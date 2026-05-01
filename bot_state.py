import json
import os
import time
from pathlib import Path

from bot_i18n import SUPPORTED_UI_LANGUAGES
from bot_i18n import SUPPORTED_VOICE_LANGUAGES


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


def default_stt_language():
    return os.environ.get("STT_DEFAULT_LANGUAGE", "auto")


def default_codex_workdir():
    return os.environ.get("CODEX_WORKDIR", str(Path.home()))


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
