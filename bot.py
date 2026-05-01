#!/usr/bin/env python3
import json
import os
import re
import shlex
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from bot_i18n import ABOUT_BUTTONS
from bot_i18n import SUPPORTED_UI_LANGUAGES
from bot_i18n import bot_commands
from bot_i18n import help_text as localized_help_text
from bot_i18n import language_keyboard
from bot_i18n import main_keyboard as localized_main_keyboard
from bot_i18n import translate
from bot_state import ENV_PATH
from bot_state import ROOT
from bot_state import UPLOADS_DIR
from bot_state import append_history
from bot_state import chat_history_path
from bot_state import cleanup_old_uploads
from bot_state import clear_chat_state
from bot_state import ensure_state_dirs
from bot_state import has_ui_language
from bot_state import read_chat_workdir
from bot_state import read_offset
from bot_state import read_session_id
from bot_state import read_stt_language
from bot_state import read_ui_language
from bot_state import resolve_requested_workdir
from bot_state import session_path
from bot_state import settings_path
from bot_state import workdir_path
from bot_state import write_chat_workdir
from bot_state import write_offset
from bot_state import write_session_id
from bot_state import write_stt_language
from bot_state import write_ui_language
from bot_telegram import require_env
from bot_telegram import send_message
from bot_telegram import telegram
from bot_telegram import telegram_file_url


SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{36})")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

state_lock = threading.Lock()
current_process = None
current_chat_id = None
current_started_at = None
current_task_cancelled = False


def load_env(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def stt_command_config():
    command = os.environ.get("STT_COMMAND")
    if not command:
        venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return [str(venv_python), str(ROOT / "scripts" / "transcribe_voice.py")]
    return shlex.split(command)


def stt_model():
    return os.environ.get("STT_MODEL", "base")


def stt_device():
    return os.environ.get("STT_DEVICE", "cpu")


def stt_compute_type():
    return os.environ.get("STT_COMPUTE_TYPE", "int8")


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


def t(chat_id, key, **values):
    return translate(read_ui_language(chat_id), key, **values)


def safe_filename(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "upload")
    return cleaned.strip("._") or "upload"


def extension_from_file_path(file_path, fallback):
    suffix = Path(file_path or "").suffix
    return suffix if suffix else fallback


def download_telegram_file(file_id, filename_hint, fallback_ext):
    file_info = telegram("getFile", {"file_id": file_id}, timeout=30)
    file_path = file_info["file_path"]
    ext = extension_from_file_path(file_path, fallback_ext)
    filename = f"{int(time.time())}_{safe_filename(filename_hint)}{ext}"
    local_path = UPLOADS_DIR / filename
    with urllib.request.urlopen(telegram_file_url(file_path), timeout=120) as response:
        local_path.write_bytes(response.read())
    return local_path


def collect_attachments(message):
    attachments = []
    if message.get("photo"):
        photo = max(message["photo"], key=lambda item: item.get("file_size", 0))
        path = download_telegram_file(photo["file_id"], f"photo_{photo.get('file_unique_id', 'image')}", ".jpg")
        attachments.append({"kind": "image", "path": path})
    if message.get("video"):
        video = message["video"]
        path = download_telegram_file(video["file_id"], video.get("file_name") or "video", ".mp4")
        attachments.append({"kind": "video", "path": path})
    if message.get("voice"):
        voice = message["voice"]
        path = download_telegram_file(voice["file_id"], f"voice_{voice.get('file_unique_id', 'audio')}", ".oga")
        attachments.append({"kind": "voice", "path": path})
    if message.get("audio"):
        audio = message["audio"]
        path = download_telegram_file(audio["file_id"], audio.get("file_name") or "audio", ".mp3")
        attachments.append({"kind": "audio", "path": path})
    if message.get("document"):
        document = message["document"]
        mime_type = document.get("mime_type", "")
        path = download_telegram_file(document["file_id"], document.get("file_name") or "document", "")
        kind = "image" if mime_type.startswith("image/") else "file"
        attachments.append({"kind": kind, "path": path})
    return attachments


def transcribe_audio(path, language):
    cmd = stt_command_config() + [
        str(path),
        "--model",
        stt_model(),
        "--language",
        language,
        "--device",
        stt_device(),
        "--compute-type",
        stt_compute_type(),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=codex_timeout(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:] or "speech transcription failed")
    payload = json.loads(result.stdout.strip())
    return payload


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


def prompt_with_attachments(text, attachments):
    text = text or "Опиши вложение."
    if not attachments:
        return text
    non_images = [item for item in attachments if item["kind"] != "image"]
    if not non_images:
        return text
    lines = [text, "", "Локальные вложения:"]
    for item in non_images:
        lines.append(f"- {item['kind']}: {item['path']}")
    lines.append("Если нужно, используй локальные инструменты для чтения этих файлов.")
    return "\n".join(lines)


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


def main_keyboard(chat_id):
    return localized_main_keyboard(read_ui_language(chat_id))


def ask_ui_language(chat_id):
    send_message(chat_id, t(chat_id, "ask_ui_language"), reply_markup=language_keyboard())


def handle_about(chat_id):
    send_message(chat_id, t(chat_id, "about"), reply_markup=main_keyboard(chat_id))


def handle_status(chat_id):
    with state_lock:
        running = current_started_at is not None
        started_at = current_started_at
    if running:
        send_message(chat_id, t(chat_id, "status_running", duration=format_duration(started_at)))
    else:
        session_id = read_session_id(chat_id)
        if session_id:
            send_message(chat_id, t(chat_id, "status_idle_session", session_id=session_id))
        else:
            send_message(chat_id, t(chat_id, "status_idle_empty"))


def handle_cancel(chat_id):
    stopped = stop_current_task()
    if stopped:
        send_message(chat_id, t(chat_id, "response_stopped"))
        return
    send_message(chat_id, t(chat_id, "no_response_to_stop"))


def handle_session(chat_id):
    session_id = read_session_id(chat_id)
    if session_id:
        send_message(chat_id, t(chat_id, "session_current", session_id=session_id))
    else:
        send_message(chat_id, t(chat_id, "session_empty"))


def handle_pwd(chat_id):
    send_message(chat_id, t(chat_id, "pwd", workdir=read_chat_workdir(chat_id)))


def handle_cd(chat_id, text):
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        send_message(chat_id, t(chat_id, "cd_usage", workdir=read_chat_workdir(chat_id)))
        return
    with state_lock:
        running = current_started_at is not None
    if running:
        send_message(chat_id, t(chat_id, "cd_running"))
        return
    path = resolve_requested_workdir(chat_id, parts[1])
    if not path.exists():
        send_message(chat_id, t(chat_id, "dir_missing", path=path))
        return
    if not path.is_dir():
        send_message(chat_id, t(chat_id, "not_dir", path=path))
        return
    write_chat_workdir(chat_id, path)
    session_id = read_session_id(chat_id)
    if session_id:
        send_message(chat_id, t(chat_id, "cd_kept", path=path))
    else:
        send_message(chat_id, t(chat_id, "cd_no_session", path=path))


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


def handle_new(chat_id, text):
    parts = text.split(maxsplit=1)
    target_path = parts[1].strip() if len(parts) == 2 else ""
    if target_path:
        path = resolve_requested_workdir(chat_id, target_path)
        if not path.exists():
            send_message(chat_id, t(chat_id, "dir_missing", path=path))
            return
        if not path.is_dir():
            send_message(chat_id, t(chat_id, "not_dir", path=path))
            return
        write_chat_workdir(chat_id, path)

    stopped = stop_current_task()
    clear_chat_state(chat_id)
    workdir = read_chat_workdir(chat_id)
    prefix = t(chat_id, "cancelled_prefix") if stopped else ""
    send_message(chat_id, t(chat_id, "new_session", prefix=prefix, workdir=workdir))


def handle_reset(chat_id):
    clear_chat_state(chat_id)
    send_message(chat_id, t(chat_id, "reset_done"))


def handle_language(chat_id, language):
    write_stt_language(chat_id, language)
    label = "auto-detect" if language == "auto" else language
    send_message(chat_id, t(chat_id, "voice_language", language=label))


def handle_ui_language(chat_id, text):
    parts = text.split(maxsplit=1)
    language = ""
    if len(parts) == 2:
        language = parts[1].strip().lower()
    elif text.lower() in SUPPORTED_UI_LANGUAGES:
        language = text.lower()
    if language not in SUPPORTED_UI_LANGUAGES:
        send_message(chat_id, t(chat_id, "ui_language_usage"))
        return
    write_ui_language(chat_id, language)
    send_message(chat_id, t(chat_id, "ui_language_set"), reply_markup=main_keyboard(chat_id))


def attach_latest_session(chat_id):
    stop_current_task()
    last_path = last_message_path()
    if last_path and last_path.exists():
        last_path.unlink()
    cmd = codex_resume_last_command()
    try:
        process = subprocess.run(
            cmd,
            cwd=read_chat_workdir(chat_id),
            input="Reply exactly: session attached",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=codex_timeout(),
        )
    except Exception as exc:
        send_message(chat_id, t(chat_id, "resume_latest_error", error=exc))
        return
    if process.returncode != 0:
        send_message(chat_id, t(chat_id, "resume_latest_failed", output=process.stdout[-2500:]))
        return
    session_id = parse_session_id(process.stdout)
    if not session_id:
        send_message(chat_id, t(chat_id, "resume_latest_no_id"))
        return
    write_session_id(chat_id, session_id)
    send_message(chat_id, t(chat_id, "resume_latest_ok", session_id=session_id))


def handle_resume(chat_id, text):
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        send_message(chat_id, t(chat_id, "resume_usage"))
        return
    target = parts[1].strip()
    if target.lower() == "last":
        attach_latest_session(chat_id)
        return
    if not valid_session_id(target):
        send_message(chat_id, t(chat_id, "resume_bad_id"))
        return
    stop_current_task()
    write_session_id(chat_id, target)
    send_message(chat_id, t(chat_id, "resume_ok", session_id=target))


def transcribe_voice_attachments(chat_id, attachments):
    language = read_stt_language(chat_id)
    transcripts = []
    rest = []
    for item in attachments:
        if item["kind"] not in {"voice", "audio"}:
            rest.append(item)
            continue
        payload = transcribe_audio(item["path"], language)
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


def prompt_with_transcripts(prompt, transcripts):
    if not transcripts:
        return prompt
    lines = [prompt or "Ответь на голосовое сообщение.", "", "Расшифровка голосовых сообщений:"]
    for index, transcript in enumerate(transcripts, start=1):
        lines.append(
            f"{index}. language={transcript['language']} path={transcript['path']}\n{transcript['text']}"
        )
    return "\n".join(lines)


def run_codex(chat_id, prompt, attachments=None):
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


def allowed_user_id():
    return int(require_env("TELEGRAM_ALLOWED_USER_ID"))


def set_bot_commands():
    telegram("setMyCommands", {"commands": bot_commands("en")}, timeout=30)
    telegram("setMyCommands", {"commands": bot_commands("ru"), "language_code": "ru"}, timeout=30)


def handle_message(message):
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = sender.get("id")
    text = (message.get("text") or message.get("caption") or "").strip()

    if not chat_id:
        return
    if user_id != allowed_user_id():
        send_message(chat_id, t(chat_id, "access_denied"))
        return

    if text == "/start":
        if not has_ui_language(chat_id):
            ask_ui_language(chat_id)
        else:
            send_message(chat_id, localized_help_text(read_ui_language(chat_id)), reply_markup=main_keyboard(chat_id))
        return
    if text == "/help":
        send_message(chat_id, localized_help_text(read_ui_language(chat_id)), reply_markup=main_keyboard(chat_id))
        return
    if text in set(ABOUT_BUTTONS.values()) or text == "/about":
        handle_about(chat_id)
        return
    if text.lower() in {"ru", "en"}:
        handle_ui_language(chat_id, text)
        return
    if text == "/lang" or text.startswith("/lang "):
        handle_ui_language(chat_id, text)
        return
    if text == "/status":
        handle_status(chat_id)
        return
    if text == "/cancel":
        handle_cancel(chat_id)
        return
    if text == "/session":
        handle_session(chat_id)
        return
    if text in {"/pwd", "pwd"}:
        handle_pwd(chat_id)
        return
    if text in {"/cd", "cd"} or text.startswith("/cd ") or text.startswith("cd "):
        handle_cd(chat_id, text)
        return
    if text == "/new" or text.startswith("/new "):
        handle_new(chat_id, text)
        return
    if text.startswith("/resume"):
        handle_resume(chat_id, text)
        return
    if text == "/reset":
        handle_reset(chat_id)
        return
    if text in {"/ru", "/en", "/uk", "/auto"}:
        handle_language(chat_id, text[1:])
        return

    try:
        cleanup_old_uploads()
        attachments = collect_attachments(message)
    except Exception as exc:
        send_message(chat_id, t(chat_id, "download_failed", error=exc))
        return
    if not text and not attachments:
        return

    threading.Thread(target=run_codex, args=(chat_id, text, attachments), daemon=True).start()


def poll_loop():
    offset = read_offset()
    while True:
        try:
            updates = telegram(
                "getUpdates",
                {"timeout": 50, "offset": offset, "allowed_updates": json.dumps(["message"])},
                timeout=60,
            )
            for update in updates:
                offset = max(offset, update["update_id"] + 1)
                write_offset(offset)
                message = update.get("message")
                if message:
                    handle_message(message)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Telegram network error: {exc}", flush=True)
            time.sleep(5)
        except Exception as exc:
            print(f"Bot loop error: {exc}", flush=True)
            time.sleep(5)


def main():
    load_env(ENV_PATH)
    require_env("TELEGRAM_BOT_TOKEN")
    require_env("TELEGRAM_ALLOWED_USER_ID")
    ensure_state_dirs()
    telegram(
        "deleteWebhook",
        {"drop_pending_updates": "true" if bool_env("DROP_PENDING_UPDATES_ON_START") else "false"},
        timeout=30,
    )
    set_bot_commands()
    me = telegram("getMe", timeout=30)
    print(f"Bot started as @{me.get('username', 'unknown')}", flush=True)
    poll_loop()


if __name__ == "__main__":
    main()
