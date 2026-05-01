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
WORKDIRS_DIR = STATE_DIR / "workdirs"
SETTINGS_DIR = STATE_DIR / "settings"
OFFSET_PATH = STATE_DIR / "offset.txt"
MAX_TELEGRAM_MESSAGE = 3900
SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{36})")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MDV2_SPECIALS = set("_*[]()~`>#+-=|{}.!")
SUPPORTED_UI_LANGUAGES = {"en", "ru"}
SUPPORTED_VOICE_LANGUAGES = {"auto", "ru", "en", "uk"}

MESSAGES = {
    "en": {
        "access_denied": "Access denied.",
        "ask_ui_language": "Choose bot interface language:",
        "ui_language_set": "Bot interface language: English.",
        "ui_language_usage": "Use: /lang ru or /lang en",
        "unknown_ui_language": "Supported interface languages: ru, en",
        "status_running": "Codex is running for {duration}.",
        "status_idle_session": "No Codex task is running.\nCurrent session: {session_id}",
        "status_idle_empty": "No Codex task is running.\nNo saved session yet.",
        "response_stopped": "Response stopped.",
        "no_response_to_stop": "No running response to stop.",
        "session_current": "Current Codex session:\n{session_id}",
        "session_empty": "No saved Codex session yet. Send a message to start one.",
        "pwd": "Current Codex working directory:\n{workdir}",
        "cd_usage": "Current Codex working directory:\n{workdir}\n\nUse: cd <path>",
        "cd_running": "Codex is running. Use /cancel first, then cd <path>.",
        "dir_missing": "Directory does not exist:\n{path}",
        "not_dir": "That path is not a directory:\n{path}",
        "cd_kept": "Working directory set:\n{path}\n\nCurrent session kept. The next message will continue there.",
        "cd_no_session": "Working directory set:\n{path}\n\nNo saved session yet. The next message will start there.",
        "new_session": "{prefix}New Codex session will start on the next message.\nWorking directory:\n{workdir}",
        "cancelled_prefix": "Cancelled running task. ",
        "reset_done": "Codex session was reset. The next message will start a fresh session.",
        "voice_language": "Voice transcription language: {language}",
        "resume_latest_error": "Could not resume latest session: {error}",
        "resume_latest_failed": "Could not resume latest session.\n\n{output}",
        "resume_latest_no_id": "Latest session resumed, but I could not read its session id.",
        "resume_latest_ok": "Attached to latest Codex session:\n{session_id}",
        "resume_usage": "Use: /resume <session_id>\nOr: /resume last",
        "resume_bad_id": "That does not look like a Codex session UUID.",
        "resume_ok": "Attached to Codex session:\n{session_id}",
        "transcribing": "Transcribing voice ({language})...",
        "transcribe_failed": "Could not transcribe voice: {error}",
        "already_running": "Codex is already running. Use /status or /cancel.",
        "starting": "Starting Codex session...",
        "continuing": "Continuing Codex session...",
        "timeout": "Codex timed out after {timeout}s.\n\n{output}",
        "empty_output": "Codex finished with no text output.",
        "codex_exit": "Codex exited with code {code}.\n\n{output}",
        "bot_error": "Bot error: {error}",
        "download_failed": "Could not download attachment: {error}",
    },
    "ru": {
        "access_denied": "Доступ запрещён.",
        "ask_ui_language": "Choose bot interface language:",
        "ui_language_set": "Язык интерфейса бота: русский.",
        "ui_language_usage": "Используй: /lang ru или /lang en",
        "unknown_ui_language": "Доступные языки интерфейса: ru, en",
        "status_running": "Codex работает уже {duration}.",
        "status_idle_session": "Сейчас Codex не выполняет задачу.\nТекущая сессия: {session_id}",
        "status_idle_empty": "Сейчас Codex не выполняет задачу.\nСохранённой сессии пока нет.",
        "response_stopped": "Ответ остановлен.",
        "no_response_to_stop": "Сейчас нечего останавливать.",
        "session_current": "Текущая Codex-сессия:\n{session_id}",
        "session_empty": "Сохранённой Codex-сессии пока нет. Отправь сообщение, чтобы начать.",
        "pwd": "Текущая рабочая папка Codex:\n{workdir}",
        "cd_usage": "Текущая рабочая папка Codex:\n{workdir}\n\nИспользуй: cd <path>",
        "cd_running": "Codex сейчас работает. Сначала /cancel, потом cd <path>.",
        "dir_missing": "Папка не существует:\n{path}",
        "not_dir": "Это не папка:\n{path}",
        "cd_kept": "Рабочая папка установлена:\n{path}\n\nТекущая сессия сохранена. Следующее сообщение продолжит её там.",
        "cd_no_session": "Рабочая папка установлена:\n{path}\n\nСессии пока нет. Следующее сообщение стартует там.",
        "new_session": "{prefix}Новая Codex-сессия начнётся со следующего сообщения.\nРабочая папка:\n{workdir}",
        "cancelled_prefix": "Текущая задача остановлена. ",
        "reset_done": "Codex-сессия сброшена. Следующее сообщение начнёт свежую сессию.",
        "voice_language": "Язык распознавания голоса: {language}",
        "resume_latest_error": "Не получилось продолжить последнюю сессию: {error}",
        "resume_latest_failed": "Не получилось продолжить последнюю сессию.\n\n{output}",
        "resume_latest_no_id": "Последняя сессия продолжена, но я не смог прочитать её session id.",
        "resume_latest_ok": "Подключилась к последней Codex-сессии:\n{session_id}",
        "resume_usage": "Используй: /resume <session_id>\nИли: /resume last",
        "resume_bad_id": "Это не похоже на UUID Codex-сессии.",
        "resume_ok": "Подключилась к Codex-сессии:\n{session_id}",
        "transcribing": "Расшифровываю голос ({language})...",
        "transcribe_failed": "Не получилось расшифровать голос: {error}",
        "already_running": "Codex уже работает. Используй /status или /cancel.",
        "starting": "Запускаю Codex-сессию...",
        "continuing": "Продолжаю Codex-сессию...",
        "timeout": "Codex не ответил за {timeout}s.\n\n{output}",
        "empty_output": "Codex завершился без текстового ответа.",
        "codex_exit": "Codex завершился с кодом {code}.\n\n{output}",
        "bot_error": "Ошибка бота: {error}",
        "download_failed": "Не получилось скачать вложение: {error}",
    },
}

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


def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def telegram(method, data=None, timeout=60):
    token = require_env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = {}
    for key, value in (data or {}).items():
        payload[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
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


def send_message(chat_id, text, reply_markup=None):
    text = text or "(empty response)"
    for start in range(0, len(text), MAX_TELEGRAM_MESSAGE):
        chunk = text[start : start + MAX_TELEGRAM_MESSAGE]
        payload = {"chat_id": chat_id, "text": chunk}
        if reply_markup and start == 0:
            payload["reply_markup"] = reply_markup
        parse_mode = telegram_parse_mode()
        if parse_mode == "MarkdownV2":
            try:
                markdown_payload = dict(payload)
                markdown_payload["text"] = markdown_to_telegram(chunk)
                markdown_payload["parse_mode"] = "MarkdownV2"
                telegram(
                    "sendMessage",
                    markdown_payload,
                    timeout=30,
                )
                continue
            except Exception as exc:
                print(f"MarkdownV2 send failed, falling back to plain text: {exc}", flush=True)
        telegram("sendMessage", payload, timeout=30)


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
    return os.environ.get("STT_DEFAULT_LANGUAGE", "auto")


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


def ensure_state_dirs():
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)
    WORKDIRS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def chat_history_path(chat_id):
    ensure_state_dirs()
    return CHATS_DIR / f"{chat_id}.jsonl"


def session_path(chat_id):
    ensure_state_dirs()
    return SESSIONS_DIR / f"{chat_id}.txt"


def language_path(chat_id):
    ensure_state_dirs()
    return LANGUAGES_DIR / f"{chat_id}.txt"


def settings_path(chat_id):
    ensure_state_dirs()
    return SETTINGS_DIR / f"{chat_id}.json"


def workdir_path(chat_id):
    ensure_state_dirs()
    return WORKDIRS_DIR / f"{chat_id}.txt"


def default_chat_settings():
    return {"voice_language": default_stt_language(), "ui_language": ""}


def read_chat_settings(chat_id):
    settings = default_chat_settings()
    path = settings_path(chat_id)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update({key: value for key, value in loaded.items() if isinstance(value, str)})
        except json.JSONDecodeError:
            pass
    if settings.get("voice_language") not in SUPPORTED_VOICE_LANGUAGES:
        settings["voice_language"] = default_stt_language()
    if settings.get("ui_language") not in SUPPORTED_UI_LANGUAGES:
        settings["ui_language"] = ""
    return settings


def write_chat_settings(chat_id, settings):
    merged = read_chat_settings(chat_id)
    merged.update(settings)
    settings_path(chat_id).write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_ui_language(chat_id):
    return read_chat_settings(chat_id).get("ui_language") or "en"


def has_ui_language(chat_id):
    return bool(read_chat_settings(chat_id).get("ui_language"))


def write_ui_language(chat_id, language):
    write_chat_settings(chat_id, {"ui_language": language})


def t(chat_id, key, **values):
    language = read_ui_language(chat_id)
    template = MESSAGES.get(language, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))
    return template.format(**values)


def default_codex_workdir():
    return os.environ.get("CODEX_WORKDIR", str(Path.home()))


def read_chat_workdir(chat_id):
    path = workdir_path(chat_id)
    if not path.exists():
        return default_codex_workdir()
    return path.read_text(encoding="utf-8").strip() or default_codex_workdir()


def write_chat_workdir(chat_id, workdir):
    workdir_path(chat_id).write_text(str(workdir), encoding="utf-8")


def resolve_requested_workdir(chat_id, raw_path):
    value = os.path.expandvars((raw_path or "").strip())
    if not value:
        return Path(read_chat_workdir(chat_id))
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(read_chat_workdir(chat_id)) / path
    return path.resolve()


def read_stt_language(chat_id):
    return read_chat_settings(chat_id).get("voice_language") or default_stt_language()


def write_stt_language(chat_id, language):
    write_chat_settings(chat_id, {"voice_language": language})


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


def help_text(chat_id):
    if read_ui_language(chat_id) == "ru":
        return (
            "Codex bridge online.\n\n"
            "Отправь текст, и я продолжу ту же Codex-сессию для этого Telegram-чата.\n"
            "Фото передаются как изображения. Видео и файлы сохраняются локально и передаются путями.\n"
            "Голосовые сообщения расшифровываются локально перед отправкой в Codex.\n"
            "pwd или /pwd - показать рабочую папку Codex\n"
            "cd <path> или /cd <path> - сменить рабочую папку и сохранить текущую сессию\n"
            "/new [path] - остановить текущую задачу, забыть сессию, опционально сменить папку\n"
            "/status - показать состояние\n"
            "/cancel - остановить текущий ответ Codex\n"
            "/session - показать текущую Codex-сессию\n"
            "/resume <session_id> - остановить ответ и переключиться на другую Codex-сессию\n"
            "/resume last - остановить ответ и переключиться на последнюю Codex-сессию\n"
            "/ru /en /uk /auto - язык распознавания голоса\n"
            "/lang ru или /lang en - язык интерфейса бота\n"
            "/reset - начать свежую Codex-сессию\n"
            "/help - показать это сообщение"
        )
    return (
        "Codex bridge is online.\n\n"
        "Send any text and I will continue the same Codex session for this Telegram chat.\n"
        "Photos are attached as images. Videos and files are saved locally and sent as paths.\n"
        "Voice messages are transcribed locally before they are sent to Codex.\n"
        "pwd or /pwd - show current Codex working directory\n"
        "cd <path> or /cd <path> - switch working directory and keep current session\n"
        "/new [path] - cancel current task, forget session, optionally switch directory\n"
        "/status - show current task\n"
        "/cancel - stop the current Codex response\n"
        "/session - show current Codex session\n"
        "/resume <session_id> - stop current response and switch to another Codex session\n"
        "/resume last - stop current response and switch to the latest Codex session\n"
        "/ru /en /uk /auto - voice transcription language\n"
        "/lang ru or /lang en - bot interface language\n"
        "/reset - start a fresh Codex session for this chat\n"
        "/help - show this message"
    )


def language_keyboard():
    return {"keyboard": [["ru", "en"]], "resize_keyboard": True, "one_time_keyboard": True}


def ask_ui_language(chat_id):
    send_message(chat_id, t(chat_id, "ask_ui_language"), reply_markup=language_keyboard())


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
    send_message(chat_id, t(chat_id, "ui_language_set"))


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
            send_message(chat_id, help_text(chat_id))
        return
    if text == "/help":
        send_message(chat_id, help_text(chat_id))
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
    me = telegram("getMe", timeout=30)
    print(f"Bot started as @{me.get('username', 'unknown')}", flush=True)
    poll_loop()


if __name__ == "__main__":
    main()
