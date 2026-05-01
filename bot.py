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
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
STATE_DIR = ROOT / "state"
CHATS_DIR = STATE_DIR / "chats"
SESSIONS_DIR = STATE_DIR / "sessions"
UPLOADS_DIR = STATE_DIR / "uploads"
LANGUAGES_DIR = STATE_DIR / "languages"
OFFSET_PATH = STATE_DIR / "offset.txt"
MAX_TELEGRAM_MESSAGE = 3900
SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{36})")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MDV2_SPECIALS = set("_*[]()~`>#+-=|{}.!")

state_lock = threading.Lock()
current_process = None
current_chat_id = None
current_started_at = None


def load_env(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def telegram(method, data=None, timeout=60):
    token = require_env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = urllib.parse.urlencode(data or {}).encode("utf-8")
    request = urllib.request.Request(url, data=encoded)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    parsed = json.loads(payload)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {parsed!r}")
    return parsed["result"]


def telegram_file_url(file_path):
    token = require_env("TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


def telegram_parse_mode():
    return os.environ.get("TELEGRAM_PARSE_MODE", "MarkdownV2").strip()


def escape_markdown_v2(text):
    return "".join(f"\\{char}" if char in MDV2_SPECIALS else char for char in text)


def format_inline_markdown(line):
    placeholders = []

    def stash(value):
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    line = re.sub(r"`([^`\n]+)`", lambda m: stash(f"`{escape_markdown_v2(m.group(1))}`"), line)
    escaped = escape_markdown_v2(line)
    escaped = re.sub(r"\\\*\\\*(.+?)\\\*\\\*", r"*\1*", escaped)
    escaped = re.sub(r"(?<!\\)\\\*([^*\n]+?)\\\*", r"_\1_", escaped)
    for index, value in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", value)
    return escaped


def markdown_to_telegram(text):
    text = text or ""
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    rendered = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            body = part[3:-3]
            if body.startswith("\n"):
                body = body[1:]
            rendered.append(f"```{escape_markdown_v2(body)}```")
        else:
            rendered.append("\n".join(format_inline_markdown(line) for line in part.splitlines()))
    return "".join(rendered)


def send_message(chat_id, text):
    text = text or "(empty response)"
    for start in range(0, len(text), MAX_TELEGRAM_MESSAGE):
        chunk = text[start : start + MAX_TELEGRAM_MESSAGE]
        parse_mode = telegram_parse_mode()
        if parse_mode == "MarkdownV2":
            try:
                telegram(
                    "sendMessage",
                    {"chat_id": chat_id, "text": markdown_to_telegram(chunk), "parse_mode": "MarkdownV2"},
                    timeout=30,
                )
                continue
            except Exception as exc:
                print(f"MarkdownV2 send failed, falling back to plain text: {exc}", flush=True)
        telegram("sendMessage", {"chat_id": chat_id, "text": chunk}, timeout=30)


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


def default_stt_language():
    return os.environ.get("STT_DEFAULT_LANGUAGE", "ru")


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


def codex_workdir():
    return os.environ.get("CODEX_WORKDIR", str(Path.home()))


def codex_timeout():
    return int(os.environ.get("CODEX_TIMEOUT_SECONDS", "1800"))


def ensure_state_dirs():
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)


def chat_history_path(chat_id):
    ensure_state_dirs()
    return CHATS_DIR / f"{chat_id}.jsonl"


def session_path(chat_id):
    ensure_state_dirs()
    return SESSIONS_DIR / f"{chat_id}.txt"


def language_path(chat_id):
    ensure_state_dirs()
    return LANGUAGES_DIR / f"{chat_id}.txt"


def read_stt_language(chat_id):
    path = language_path(chat_id)
    if not path.exists():
        return default_stt_language()
    return path.read_text(encoding="utf-8").strip() or default_stt_language()


def write_stt_language(chat_id, language):
    language_path(chat_id).write_text(language, encoding="utf-8")


def read_session_id(chat_id):
    path = session_path(chat_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_session_id(chat_id, session_id):
    if session_id:
        session_path(chat_id).write_text(session_id, encoding="utf-8")


def clear_chat_state(chat_id):
    for path in (chat_history_path(chat_id), session_path(chat_id)):
        if path.exists():
            path.unlink()


def append_history(chat_id, role, text):
    record = {"ts": int(time.time()), "role": role, "text": text}
    path = chat_history_path(chat_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_history_records(chat_id):
    path = chat_history_path(chat_id)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def read_offset():
    try:
        return int(OFFSET_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_offset(offset):
    ensure_state_dirs()
    OFFSET_PATH.write_text(str(offset), encoding="utf-8")


def upload_retention_seconds():
    return int(float(os.environ.get("UPLOAD_RETENTION_HOURS", "48")) * 3600)


def cleanup_old_uploads():
    ensure_state_dirs()
    cutoff = time.time() - upload_retention_seconds()
    for path in UPLOADS_DIR.glob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


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


def help_text():
    return (
        "Codex bridge is online.\n\n"
        "Send any text and I will continue the same Codex session for this Telegram chat.\n"
        "Photos are attached as images. Videos and files are saved locally and sent as paths.\n"
        "Voice messages are transcribed locally before they are sent to Codex.\n"
        "/status - show current task\n"
        "/cancel - terminate current Codex task\n"
        "/session - show current Codex session\n"
        "/resume <session_id> - switch this chat to another Codex session\n"
        "/resume last - switch this chat to the latest Codex session\n"
        "/ru /en /uk /auto - voice transcription language\n"
        "/reset - start a fresh Codex session for this chat\n"
        "/help - show this message"
    )


def handle_status(chat_id):
    with state_lock:
        running = current_started_at is not None
        started_at = current_started_at
    if running:
        send_message(chat_id, f"Codex is running for {format_duration(started_at)}.")
    else:
        session_id = read_session_id(chat_id)
        if session_id:
            send_message(chat_id, f"No Codex task is running.\nCurrent session: {session_id}")
        else:
            send_message(chat_id, "No Codex task is running.\nNo saved session yet.")


def handle_cancel(chat_id):
    with state_lock:
        process = current_process
    if process is None or process.poll() is not None:
        with state_lock:
            preparing = current_started_at is not None
        if preparing:
            send_message(chat_id, "Task is preparing or transcribing and cannot be cancelled yet.")
        else:
            send_message(chat_id, "No running Codex task to cancel.")
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    send_message(chat_id, "Codex task was cancelled.")


def handle_session(chat_id):
    session_id = read_session_id(chat_id)
    if session_id:
        send_message(chat_id, f"Current Codex session:\n{session_id}")
    else:
        send_message(chat_id, "No saved Codex session yet. Send a message to start one.")


def handle_reset(chat_id):
    clear_chat_state(chat_id)
    send_message(chat_id, "Codex session was reset. The next message will start a fresh session.")


def handle_language(chat_id, language):
    write_stt_language(chat_id, language)
    label = "auto-detect" if language == "auto" else language
    send_message(chat_id, f"Voice transcription language: {label}")


def attach_latest_session(chat_id):
    last_path = last_message_path()
    if last_path and last_path.exists():
        last_path.unlink()
    cmd = codex_resume_last_command()
    try:
        process = subprocess.run(
            cmd,
            cwd=codex_workdir(),
            input="Reply exactly: session attached",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=codex_timeout(),
        )
    except Exception as exc:
        send_message(chat_id, f"Could not resume latest session: {exc}")
        return
    if process.returncode != 0:
        send_message(chat_id, f"Could not resume latest session.\n\n{process.stdout[-2500:]}")
        return
    session_id = parse_session_id(process.stdout)
    if not session_id:
        send_message(chat_id, "Latest session resumed, but I could not read its session id.")
        return
    write_session_id(chat_id, session_id)
    send_message(chat_id, f"Attached to latest Codex session:\n{session_id}")


def handle_resume(chat_id, text):
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        send_message(chat_id, "Use: /resume <session_id>\nOr: /resume last")
        return
    target = parts[1].strip()
    if target.lower() == "last":
        attach_latest_session(chat_id)
        return
    if not valid_session_id(target):
        send_message(chat_id, "That does not look like a Codex session UUID.")
        return
    write_session_id(chat_id, target)
    send_message(chat_id, f"Attached to Codex session:\n{target}")


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
    global current_process, current_chat_id, current_started_at

    with state_lock:
        if current_started_at is not None:
            send_message(chat_id, "Codex is already running. Use /status or /cancel.")
            return
        current_chat_id = chat_id
        current_started_at = time.time()

    attachments = attachments or []
    try:
        voice_items = [item for item in attachments if item["kind"] in {"voice", "audio"}]
        if voice_items:
            send_message(chat_id, f"Transcribing voice ({read_stt_language(chat_id)})...")
        transcripts, attachments = transcribe_voice_attachments(chat_id, attachments)
        prompt = prompt_with_transcripts(prompt, transcripts)
    except Exception as exc:
        send_message(chat_id, f"Could not transcribe voice: {exc}")
        with state_lock:
            current_process = None
            current_chat_id = None
            current_started_at = None
        return

    prompt = prompt_with_attachments(prompt, attachments)
    append_history(chat_id, "user", prompt)
    session_id = read_session_id(chat_id)
    send_message(chat_id, "Continuing Codex session..." if session_id else "Starting Codex session...")
    last_path = last_message_path()
    if last_path and last_path.exists():
        last_path.unlink()
    cmd = codex_resume_command(session_id) if session_id else codex_command_with_output_file()
    image_paths = [item["path"] for item in attachments if item["kind"] == "image"]
    cmd = add_images_to_command(cmd, image_paths)
    timeout = codex_timeout()
    workdir = codex_workdir()

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
            send_message(chat_id, f"Codex timed out after {timeout}s.\n\n{output[-3000:]}")
            return

        if process.returncode == 0:
            write_session_id(chat_id, parse_session_id(output))
            response = read_last_message(last_path) or extract_final_answer(output) or "Codex finished with no text output."
            append_history(chat_id, "assistant", response)
            send_message(chat_id, response)
        else:
            send_message(chat_id, f"Codex exited with code {process.returncode}.\n\n{output[-3500:]}")
    except Exception as exc:
        send_message(chat_id, f"Bot error: {exc}")
    finally:
        with state_lock:
            current_process = None
            current_chat_id = None
            current_started_at = None


def allowed_user_id():
    return int(require_env("TELEGRAM_ALLOWED_USER_ID"))


def handle_message(message):
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = sender.get("id")
    text = (message.get("text") or message.get("caption") or "").strip()

    if not chat_id:
        return
    if user_id != allowed_user_id():
        send_message(chat_id, "Access denied.")
        return

    if text in {"/start", "/help"}:
        send_message(chat_id, help_text())
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
        send_message(chat_id, f"Could not download attachment: {exc}")
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
                {"timeout": 50, "offset": offset, "allowed_updates": json.dumps(["message"])} ,
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
    me = telegram("getMe", timeout=30)
    print(f"Bot started as @{me.get('username', 'unknown')}", flush=True)
    poll_loop()


if __name__ == "__main__":
    main()
