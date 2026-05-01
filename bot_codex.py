import os
import re
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path

from bot_media import prompt_with_attachments
from bot_media import prompt_with_transcripts
from bot_media import transcribe_audio
from bot_state import ROOT
from bot_state import append_history
from bot_state import read_chat_workdir
from bot_state import read_session_id
from bot_state import read_stt_language
from bot_state import write_session_id


SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{36})")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

state_lock = threading.Lock()
current_process = None
current_chat_id = None
current_started_at = None
current_task_cancelled = False


def command_config():
    command = os.environ.get("CODEX_COMMAND")
    if not command:
        return [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--sandbox",
            "danger-full-access",
            "--skip-git-repo-check",
            "-C",
            str(Path.home()),
            "-",
        ]
    return shlex.split(command)


def resume_command_config():
    command = os.environ.get("CODEX_RESUME_COMMAND")
    if not command:
        return [
            "codex",
            "exec",
            "resume",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
        ]
    return shlex.split(command)


def last_message_path():
    value = os.environ.get("CODEX_LAST_MESSAGE_PATH")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def codex_command_with_output_file():
    cmd = command_config()
    path = last_message_path()
    if not path or "-o" in cmd or "--output-last-message" in cmd:
        return cmd
    try:
        prompt_index = cmd.index("-")
    except ValueError:
        return cmd + ["-o", str(path)]
    return cmd[:prompt_index] + ["-o", str(path)] + cmd[prompt_index:]


def add_images_to_command(cmd, image_paths):
    image_args = []
    for image_path in image_paths:
        image_args += ["-i", str(image_path)]
    if not image_args:
        return cmd
    if len(cmd) >= 2 and cmd[-1] == "-" and valid_session_id(cmd[-2]):
        return cmd[:-2] + image_args + cmd[-2:]
    try:
        prompt_index = cmd.index("-")
    except ValueError:
        return cmd + image_args
    return cmd[:prompt_index] + image_args + cmd[prompt_index:]


def command_with_cd(cmd, workdir):
    cleaned = []
    skip_next = False
    for item in cmd:
        if skip_next:
            skip_next = False
            continue
        if item in {"-C", "--cd"}:
            skip_next = True
            continue
        if item.startswith("--cd="):
            continue
        cleaned.append(item)

    try:
        prompt_index = cleaned.index("-")
    except ValueError:
        return cleaned + ["-C", str(workdir)]
    return cleaned[:prompt_index] + ["-C", str(workdir)] + cleaned[prompt_index:]


def codex_resume_command(session_id):
    cmd = resume_command_config()
    path = last_message_path()
    if path and "-o" not in cmd and "--output-last-message" not in cmd:
        cmd += ["-o", str(path)]
    return cmd + [session_id, "-"]


def codex_resume_last_command():
    cmd = resume_command_config()
    path = last_message_path()
    if path and "-o" not in cmd and "--output-last-message" not in cmd:
        cmd += ["-o", str(path)]
    return cmd + ["--last", "-"]


def read_last_message(path):
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def extract_final_answer(output):
    text = (output or "").strip()
    if not text:
        return ""
    if "\ncodex\n" in text:
        text = text.rsplit("\ncodex\n", 1)[-1]
    if "\nhook: Stop" in text:
        text = text.split("\nhook: Stop", 1)[0]
    if "\ntokens used" in text:
        text = text.split("\ntokens used", 1)[0]
    return text.strip()


def parse_session_id(output):
    match = SESSION_RE.search(output or "")
    return match.group(1) if match else ""


def valid_session_id(session_id):
    return bool(UUID_RE.fullmatch(session_id or ""))


def codex_timeout():
    return int(os.environ.get("CODEX_TIMEOUT_SECONDS", "1800"))


def popen_kwargs():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def stop_process(process):
    if os.name == "nt":
        process.terminate()
        return
    os.killpg(process.pid, signal.SIGTERM)


def force_stop_process(process):
    if os.name == "nt":
        process.kill()
        return
    os.killpg(process.pid, signal.SIGKILL)


def format_duration(started_at):
    if not started_at:
        return "0s"
    seconds = int(time.time() - started_at)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def current_task_status():
    with state_lock:
        return current_started_at is not None, current_started_at


def has_running_task():
    with state_lock:
        return current_started_at is not None


def stop_current_task():
    global current_task_cancelled

    with state_lock:
        process = current_process
        had_task = current_started_at is not None
        if had_task:
            current_task_cancelled = True
    if process is None or process.poll() is not None:
        return had_task
    stop_process(process)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        force_stop_process(process)
    return True


def task_was_cancelled():
    with state_lock:
        return current_task_cancelled


def transcribe_voice_attachments(chat_id, attachments):
    language = read_stt_language(chat_id)
    transcripts = []
    rest = []
    for item in attachments:
        if item["kind"] not in {"voice", "audio"}:
            rest.append(item)
            continue
        payload = transcribe_audio(item["path"], language, codex_timeout())
        text = payload.get("text", "").strip()
        detected = payload.get("language", language)
        probability = payload.get("language_probability")
        transcripts.append(
            {
                "path": item["path"],
                "text": text,
                "language": detected,
                "language_probability": probability,
            }
        )
    return transcripts, rest


def run_codex(chat_id, prompt, attachments, send_message, t):
    global current_process, current_chat_id, current_started_at, current_task_cancelled

    with state_lock:
        if current_started_at is not None:
            send_message(chat_id, t(chat_id, "already_running"))
            return
        current_chat_id = chat_id
        current_started_at = time.time()
        current_task_cancelled = False

    attachments = attachments or []
    try:
        voice_items = [item for item in attachments if item["kind"] in {"voice", "audio"}]
        if voice_items:
            send_message(chat_id, t(chat_id, "transcribing", language=read_stt_language(chat_id)))
        transcripts, attachments = transcribe_voice_attachments(chat_id, attachments)
        prompt = prompt_with_transcripts(prompt, transcripts)
    except Exception as exc:
        if not task_was_cancelled():
            send_message(chat_id, t(chat_id, "transcribe_failed", error=exc))
        with state_lock:
            current_process = None
            current_chat_id = None
            current_started_at = None
            current_task_cancelled = False
        return

    if task_was_cancelled():
        with state_lock:
            current_process = None
            current_chat_id = None
            current_started_at = None
            current_task_cancelled = False
        return

    prompt = prompt_with_attachments(prompt, attachments)
    append_history(chat_id, "user", prompt)
    session_id = read_session_id(chat_id)
    send_message(chat_id, t(chat_id, "continuing" if session_id else "starting"))
    last_path = last_message_path()
    if last_path and last_path.exists():
        last_path.unlink()
    workdir = read_chat_workdir(chat_id)
    cmd = codex_resume_command(session_id) if session_id else codex_command_with_output_file()
    if not session_id:
        cmd = command_with_cd(cmd, workdir)
    image_paths = [item["path"] for item in attachments if item["kind"] == "image"]
    cmd = add_images_to_command(cmd, image_paths)
    timeout = codex_timeout()

    try:
        process = subprocess.Popen(
            cmd,
            cwd=workdir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            **popen_kwargs(),
        )
        with state_lock:
            current_process = process
        try:
            output, _ = process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_process(process)
            output, _ = process.communicate(timeout=15)
            if not task_was_cancelled():
                send_message(chat_id, t(chat_id, "timeout", timeout=timeout, output=output[-3000:]))
            return

        if task_was_cancelled():
            return
        if process.returncode == 0:
            write_session_id(chat_id, parse_session_id(output))
            response = read_last_message(last_path) or extract_final_answer(output) or t(chat_id, "empty_output")
            append_history(chat_id, "assistant", response)
            send_message(chat_id, response)
        else:
            send_message(chat_id, t(chat_id, "codex_exit", code=process.returncode, output=output[-3500:]))
    except Exception as exc:
        send_message(chat_id, t(chat_id, "bot_error", error=exc))
    finally:
        with state_lock:
            current_process = None
            current_chat_id = None
            current_started_at = None
            current_task_cancelled = False
