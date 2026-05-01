#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
import urllib.error

from bot_codex import codex_resume_last_command
from bot_codex import codex_timeout
from bot_codex import current_task_status
from bot_codex import format_duration
from bot_codex import parse_session_id
from bot_codex import run_codex
from bot_codex import stop_current_task
from bot_codex import valid_session_id
from bot_i18n import ABOUT_BUTTONS
from bot_i18n import SUPPORTED_UI_LANGUAGES
from bot_i18n import bot_commands
from bot_i18n import help_text as localized_help_text
from bot_i18n import language_keyboard
from bot_i18n import main_keyboard as localized_main_keyboard
from bot_i18n import translate
from bot_media import collect_attachments
from bot_state import ENV_PATH
from bot_state import cleanup_old_uploads
from bot_state import clear_chat_state
from bot_state import ensure_state_dirs
from bot_state import has_ui_language
from bot_state import read_chat_workdir
from bot_state import read_offset
from bot_state import read_session_id
from bot_state import read_ui_language
from bot_state import resolve_requested_workdir
from bot_state import write_chat_workdir
from bot_state import write_offset
from bot_state import write_session_id
from bot_state import write_stt_language
from bot_state import write_ui_language
from bot_telegram import require_env
from bot_telegram import send_message
from bot_telegram import telegram


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


def t(chat_id, key, **values):
    return translate(read_ui_language(chat_id), key, **values)


def main_keyboard(chat_id):
    return localized_main_keyboard(read_ui_language(chat_id))


def ask_ui_language(chat_id):
    send_message(chat_id, t(chat_id, "ask_ui_language"), reply_markup=language_keyboard())


def handle_about(chat_id):
    send_message(chat_id, t(chat_id, "about"), reply_markup=main_keyboard(chat_id))


def handle_status(chat_id):
    running, started_at = current_task_status()
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
    running, _ = current_task_status()
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

    threading.Thread(target=run_codex, args=(chat_id, text, attachments, send_message, t), daemon=True).start()


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
