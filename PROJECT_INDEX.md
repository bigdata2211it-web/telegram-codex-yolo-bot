# PROJECT_INDEX.md

## Purpose

Local Telegram bridge for sending authorized messages to Codex in high-autonomy exec mode.

## Read First

- `AGENTS.md` — local pointer to global agent rules.
- `bot.py` — Telegram polling loop and Codex process runner.
- `.env.example` — required environment names without real secrets.
- `systemd/user/telegram-codex-yolo-bot.service` — user service template.
- `scripts/install_user_service.sh` — installs the user-level systemd service for the current clone path.
- `scripts/transcribe_voice.py` — local faster-whisper speech-to-text helper.

## Runtime

- Python stdlib only, no package install required.
- Bot token and allowed user id are loaded from `.env`.
- `.env` is intentionally gitignored and must not be printed or committed.
- Chat transcript is stored under `state/chats/*.jsonl`, also gitignored.
- Codex session ids are stored under `state/sessions/*.txt`; normal messages resume the same Codex session.
- Telegram media is saved under `state/uploads/`; photos are passed to Codex with `-i`, videos/files are referenced by local path in the prompt.
- Telegram voice/audio is saved under `state/uploads/`, transcribed locally with `scripts/transcribe_voice.py`, then sent to the current Codex session as text.
- Speech language is stored per chat under `state/languages/*.txt`; default is `ru`, with `/ru`, `/en`, `/uk`, `/auto`.
- Telegram update offset is stored in `state/offset.txt` so restarts do not replay old updates.
- Codex final responses are captured through `CODEX_LAST_MESSAGE_PATH` when configured.
- Telegram replies use MarkdownV2 formatting by default, with plain-text fallback.

## Commands

- Syntax check: `python3 -m py_compile bot.py`
- Voice deps: `uv venv --python python3.11 .venv && uv pip install -r requirements-voice.txt`
- Run foreground: `python3 bot.py`
- Install service: `scripts/install_user_service.sh`

## Bot Commands

- `/start` or `/help` — show short usage.
- `/status` — show whether a Codex task is running.
- `/cancel` — terminate the current Codex process.
- `/session` — show the current saved Codex session id.
- `/resume <session_id>` — attach this Telegram chat to an existing Codex session.
- `/resume last` — attach this Telegram chat to the most recent Codex session.
- `/ru`, `/en`, `/uk`, `/auto` — set voice transcription language.
- `/reset` — forget the current Codex session and transcript for this Telegram chat.
- Any text, voice, audio, photo, video, or document from the allowed user is sent to the current Codex session, or starts one if needed.

## Security

- Only `TELEGRAM_ALLOWED_USER_ID` can run Codex commands.
- The configured Codex command intentionally uses high-autonomy mode. Treat this bot like shell access to the machine.
