SUPPORTED_UI_LANGUAGES = {"en", "ru"}
SUPPORTED_VOICE_LANGUAGES = {"auto", "ru", "en", "uk"}
ABOUT_BUTTONS = {"en": "About", "ru": "О боте"}

MESSAGES = {
    "en": {
        "access_denied": "**Access denied.**",
        "ask_ui_language": "**Choose bot interface language:**",
        "ui_language_set": "**Bot interface language:** English.",
        "ui_language_usage": "Use: `/lang ru` or `/lang en`",
        "unknown_ui_language": "Supported interface languages: `ru`, `en`",
        "about": (
            "**Bot developed for free and for convenience.**\n"
            "**Contact:** https://t.me/xoskaz\n"
            "**Telegram channel:** https://t.me/gigaitools\n"
            "**GitHub:** https://github.com/bigdata2211it-web"
        ),
        "status_running": "**Codex is running** for `{duration}`.",
        "status_idle_session": "**No Codex task is running.**\n**Current session:** `{session_id}`",
        "status_idle_empty": "**No Codex task is running.**\nNo saved session yet.",
        "response_stopped": "**Response stopped.**",
        "no_response_to_stop": "No running response to stop.",
        "session_current": "**Current Codex session:**\n`{session_id}`",
        "session_empty": "No saved Codex session yet. Send a message to start one.",
        "pwd": "**Current Codex working directory:**\n`{workdir}`",
        "cd_usage": "**Current Codex working directory:**\n`{workdir}`\n\nUse: `cd <path>`",
        "cd_running": "Codex is running. Use `/cancel` first, then `cd <path>`.",
        "dir_missing": "**Directory does not exist:**\n`{path}`",
        "not_dir": "**That path is not a directory:**\n`{path}`",
        "cd_kept": "**Working directory set:**\n`{path}`\n\nCurrent session kept. The next message will continue there.",
        "cd_no_session": "**Working directory set:**\n`{path}`\n\nNo saved session yet. The next message will start there.",
        "new_session": "{prefix}**New Codex session will start on the next message.**\n**Working directory:**\n`{workdir}`",
        "cancelled_prefix": "**Cancelled running task.** ",
        "reset_done": "**Codex session was reset.** The next message will start a fresh session.",
        "voice_language": "**Voice transcription language:** `{language}`",
        "resume_latest_error": "**Could not resume latest session:** {error}",
        "resume_latest_failed": "**Could not resume latest session.**\n\n{output}",
        "resume_latest_no_id": "Latest session resumed, but I could not read its session id.",
        "resume_latest_ok": "**Attached to latest Codex session:**\n`{session_id}`",
        "resume_usage": "Use: `/resume <session_id>`\nOr: `/resume last`",
        "resume_bad_id": "That does not look like a Codex session UUID.",
        "resume_ok": "**Attached to Codex session:**\n`{session_id}`",
        "transcribing": "**Transcribing voice** (`{language}`)...",
        "transcribe_failed": "**Could not transcribe voice:** {error}",
        "already_running": "Codex is already running. Use `/status` or `/cancel`.",
        "starting": "**Starting Codex session...**",
        "continuing": "**Continuing Codex session...**",
        "timeout": "**Codex timed out after `{timeout}s`.**\n\n{output}",
        "empty_output": "Codex finished with no text output.",
        "codex_exit": "**Codex exited with code `{code}`.**\n\n{output}",
        "bot_error": "**Bot error:** {error}",
        "download_failed": "**Could not download attachment:** {error}",
    },
    "ru": {
        "access_denied": "**Доступ запрещён.**",
        "ask_ui_language": "**Choose bot interface language:**",
        "ui_language_set": "**Язык интерфейса бота:** русский.",
        "ui_language_usage": "Используй: `/lang ru` или `/lang en`",
        "unknown_ui_language": "Доступные языки интерфейса: `ru`, `en`",
        "about": (
            "**Бот разработан бесплатно и для удобства.**\n"
            "**Связь:** https://t.me/xoskaz\n"
            "**Телеграмм канал:** https://t.me/gigaitools\n"
            "**GITHUB:** https://github.com/bigdata2211it-web"
        ),
        "status_running": "**Codex работает** уже `{duration}`.",
        "status_idle_session": "**Сейчас Codex не выполняет задачу.**\n**Текущая сессия:** `{session_id}`",
        "status_idle_empty": "**Сейчас Codex не выполняет задачу.**\nСохранённой сессии пока нет.",
        "response_stopped": "**Ответ остановлен.**",
        "no_response_to_stop": "Сейчас нечего останавливать.",
        "session_current": "**Текущая Codex-сессия:**\n`{session_id}`",
        "session_empty": "Сохранённой Codex-сессии пока нет. Отправь сообщение, чтобы начать.",
        "pwd": "**Текущая рабочая папка Codex:**\n`{workdir}`",
        "cd_usage": "**Текущая рабочая папка Codex:**\n`{workdir}`\n\nИспользуй: `cd <path>`",
        "cd_running": "Codex сейчас работает. Сначала `/cancel`, потом `cd <path>`.",
        "dir_missing": "**Папка не существует:**\n`{path}`",
        "not_dir": "**Это не папка:**\n`{path}`",
        "cd_kept": "**Рабочая папка установлена:**\n`{path}`\n\nТекущая сессия сохранена. Следующее сообщение продолжит её там.",
        "cd_no_session": "**Рабочая папка установлена:**\n`{path}`\n\nСессии пока нет. Следующее сообщение стартует там.",
        "new_session": "{prefix}**Новая Codex-сессия начнётся со следующего сообщения.**\n**Рабочая папка:**\n`{workdir}`",
        "cancelled_prefix": "**Текущая задача остановлена.** ",
        "reset_done": "**Codex-сессия сброшена.** Следующее сообщение начнёт свежую сессию.",
        "voice_language": "**Язык распознавания голоса:** `{language}`",
        "resume_latest_error": "**Не получилось продолжить последнюю сессию:** {error}",
        "resume_latest_failed": "**Не получилось продолжить последнюю сессию.**\n\n{output}",
        "resume_latest_no_id": "Последняя сессия продолжена, но я не смог прочитать её session id.",
        "resume_latest_ok": "**Подключилась к последней Codex-сессии:**\n`{session_id}`",
        "resume_usage": "Используй: `/resume <session_id>`\nИли: `/resume last`",
        "resume_bad_id": "Это не похоже на UUID Codex-сессии.",
        "resume_ok": "**Подключилась к Codex-сессии:**\n`{session_id}`",
        "transcribing": "**Расшифровываю голос** (`{language}`)...",
        "transcribe_failed": "**Не получилось расшифровать голос:** {error}",
        "already_running": "Codex уже работает. Используй `/status` или `/cancel`.",
        "starting": "**Запускаю Codex-сессию...**",
        "continuing": "**Продолжаю Codex-сессию...**",
        "timeout": "**Codex не ответил за `{timeout}s`.**\n\n{output}",
        "empty_output": "Codex завершился без текстового ответа.",
        "codex_exit": "**Codex завершился с кодом `{code}`.**\n\n{output}",
        "bot_error": "**Ошибка бота:** {error}",
        "download_failed": "**Не получилось скачать вложение:** {error}",
    },
}


def translate(ui_language, key, **values):
    template = MESSAGES.get(ui_language, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))
    return template.format(**values)


def help_text(language):
    if language == "ru":
        return (
            "**Codex bridge online.**\n\n"
            "Отправь текст, и я продолжу ту же Codex-сессию для этого Telegram-чата.\n"
            "Фото передаются как изображения. Видео и файлы сохраняются локально и передаются путями.\n"
            "Голосовые сообщения расшифровываются локально перед отправкой в Codex.\n\n"
            "**Команды**\n"
            "`pwd` или `/pwd` - показать рабочую папку Codex\n"
            "`cd <path>` или `/cd <path>` - сменить рабочую папку и сохранить текущую сессию\n"
            "`/new [path]` - остановить текущую задачу, забыть сессию, опционально сменить папку\n"
            "`/status` - показать состояние\n"
            "`/cancel` - остановить текущий ответ Codex\n"
            "`/session` - показать текущую Codex-сессию\n"
            "`/resume <session_id>` - остановить ответ и переключиться на другую Codex-сессию\n"
            "`/resume last` - остановить ответ и переключиться на последнюю Codex-сессию\n"
            "`/ru` `/en` `/uk` `/auto` - язык распознавания голоса\n"
            "`/lang ru` или `/lang en` - язык интерфейса бота\n"
            "`/about` - связь, канал и GitHub\n"
            "`/reset` - начать свежую Codex-сессию\n"
            "`/help` - показать это сообщение"
        )
    return (
        "**Codex bridge is online.**\n\n"
        "Send any text and I will continue the same Codex session for this Telegram chat.\n"
        "Photos are attached as images. Videos and files are saved locally and sent as paths.\n"
        "Voice messages are transcribed locally before they are sent to Codex.\n\n"
        "**Commands**\n"
        "`pwd` or `/pwd` - show current Codex working directory\n"
        "`cd <path>` or `/cd <path>` - switch working directory and keep current session\n"
        "`/new [path]` - cancel current task, forget session, optionally switch directory\n"
        "`/status` - show current task\n"
        "`/cancel` - stop the current Codex response\n"
        "`/session` - show current Codex session\n"
        "`/resume <session_id>` - stop current response and switch to another Codex session\n"
        "`/resume last` - stop current response and switch to the latest Codex session\n"
        "`/ru` `/en` `/uk` `/auto` - voice transcription language\n"
        "`/lang ru` or `/lang en` - bot interface language\n"
        "`/about` - contact, channel, and GitHub\n"
        "`/reset` - start a fresh Codex session\n"
        "`/help` - show this message"
    )


def language_keyboard():
    return {"keyboard": [["ru", "en"]], "resize_keyboard": True, "one_time_keyboard": True}


def main_keyboard(language):
    return {"keyboard": [[ABOUT_BUTTONS.get(language, ABOUT_BUTTONS["en"])]], "resize_keyboard": True}


def bot_commands(language):
    if language == "ru":
        return [
            {"command": "help", "description": "Помощь и список команд"},
            {"command": "status", "description": "Состояние текущей задачи"},
            {"command": "cancel", "description": "Остановить текущий ответ Codex"},
            {"command": "session", "description": "Показать текущий session id"},
            {"command": "resume", "description": "Переключиться на Codex-сессию"},
            {"command": "new", "description": "Начать свежую сессию"},
            {"command": "pwd", "description": "Показать рабочую папку"},
            {"command": "cd", "description": "Сменить рабочую папку"},
            {"command": "auto", "description": "Автоопределение языка голоса"},
            {"command": "ru", "description": "Распознавать голос как русский"},
            {"command": "en", "description": "Распознавать голос как английский"},
            {"command": "uk", "description": "Распознавать голос как украинский"},
            {"command": "lang", "description": "Сменить язык интерфейса"},
            {"command": "about", "description": "Связь, канал и GitHub"},
        ]
    return [
        {"command": "help", "description": "Help and command list"},
        {"command": "status", "description": "Current task status"},
        {"command": "cancel", "description": "Stop the current Codex response"},
        {"command": "session", "description": "Show current session id"},
        {"command": "resume", "description": "Switch to a Codex session"},
        {"command": "new", "description": "Start a fresh session"},
        {"command": "pwd", "description": "Show working directory"},
        {"command": "cd", "description": "Change working directory"},
        {"command": "auto", "description": "Auto-detect voice language"},
        {"command": "ru", "description": "Transcribe voice as Russian"},
        {"command": "en", "description": "Transcribe voice as English"},
        {"command": "uk", "description": "Transcribe voice as Ukrainian"},
        {"command": "lang", "description": "Change bot interface language"},
        {"command": "about", "description": "Contact, channel, and GitHub"},
    ]
