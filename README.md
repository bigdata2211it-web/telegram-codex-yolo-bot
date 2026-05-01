# Telegram Codex Yolo Bot

Private Telegram bridge for talking to Codex from a phone.

The bot keeps one Codex session per Telegram chat, supports `/resume <session_id>`, accepts photos as Codex image inputs, saves videos/files as local paths, and transcribes voice messages locally with faster-whisper.

## Features

- Allowlisted Telegram user id.
- CLI-like Codex session continuity with `codex exec resume`.
- `/resume <session_id>` and `/resume last`.
- Photos passed with Codex `-i`.
- Videos and documents saved under `state/uploads/` and passed as local paths.
- Voice/audio transcription with local `faster-whisper`.
- Voice language commands: `/ru`, `/en`, `/uk`, `/auto`.
- Telegram MarkdownV2 formatting with plain-text fallback.
- User-level systemd service.

## Setup

```bash
cp .env.example .env
$EDITOR .env
uv venv --python python3.11 .venv
uv pip install -r requirements-voice.txt
python3 -m py_compile bot.py scripts/transcribe_voice.py
python3 bot.py
```

Required `.env` values:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_ID`
- `CODEX_WORKDIR`
- `CODEX_COMMAND`

For this bot, `CODEX_COMMAND` intentionally uses high-autonomy mode. Treat the Telegram chat as shell-level access to the machine.

## systemd

```bash
scripts/install_user_service.sh
```

Useful commands:

```bash
systemctl --user status telegram-codex-yolo-bot.service
journalctl --user -u telegram-codex-yolo-bot.service -n 80 --no-pager
systemctl --user restart telegram-codex-yolo-bot.service
```

## Bot Commands

- `/start`, `/help` — help.
- `/status` — current task/session state.
- `/cancel` — terminate the current Codex process.
- `/session` — show current Codex session id.
- `/resume <session_id>` — attach this Telegram chat to an existing Codex session.
- `/resume last` — attach to the latest Codex session.
- `/ru`, `/en`, `/uk`, `/auto` — voice transcription language.
- `/reset` — forget current Codex session and local transcript.

## Data

Ignored runtime data:

- `.env`
- `.venv/`
- `state/`

Do not commit bot tokens, chat transcripts, downloaded media, model cache, or local session ids.
