# Telegram Codex Yolo Bot

Private Telegram bridge for talking to Codex from a phone on Linux, macOS, or Windows.

## AI Agents

If you are an AI agent installing this repository for a user, read `AI_INSTALLATION.md` first. It explains what to ask for, how to choose Linux/macOS/Windows install steps, what to verify, and what to say after setup.

The bot keeps one Codex session per Telegram chat, supports `/resume <session_id>`, accepts photos as Codex image inputs, saves videos/files as local paths, and transcribes voice messages locally with faster-whisper.

## Features

- Allowlisted Telegram user id.
- CLI-like Codex session continuity with `codex exec resume`.
- `/resume <session_id>` and `/resume last`.
- Photos passed with Codex `-i`.
- Videos and documents saved under `state/uploads/` and passed as local paths.
- Voice/audio transcription with local `faster-whisper`.
- Voice language commands: `/auto`, `/ru`, `/en`, `/uk`; default is `/auto`.
- Bot interface language selection on first `/start`, with `/lang ru` and `/lang en` later.
- Persistent bottom keyboard button with bot contact/channel/GitHub links.
- Telegram command menu is registered on startup.
- Telegram MarkdownV2 formatting with plain-text fallback.
- Per-chat working directory switching with `cd <path>`, similar to changing folders before running a CLI command.
- Explicit fresh sessions with `/new` or `/new <path>`.
- OS-specific installers for Linux systemd user services, macOS LaunchAgents, and Windows Scheduled Tasks.

## Project Layout

- `bot.py` — shared cross-platform Telegram and Codex bridge.
- `AI_INSTALLATION.md` — first-read install guide for AI agents.
- `scripts/transcribe_voice.py` — shared local faster-whisper transcription helper.
- `scripts/linux/` — Linux user-service install scripts.
- `scripts/macos/` — macOS LaunchAgent install scripts.
- `scripts/windows/` — Windows Scheduled Task install scripts.
- `deploy/` — service templates for manual setup.

## Common Setup

The bot reads runtime config from `.env`. Copy the template and edit it for the OS where the bot will run.

```bash
cp .env.example .env
$EDITOR .env
```

Required `.env` values:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_ID`
- `CODEX_WORKDIR`
- `CODEX_COMMAND`

For this bot, `CODEX_COMMAND` intentionally uses high-autonomy mode. Treat the Telegram chat as shell-level access to the machine.

`CODEX_WORKDIR` is the default directory. In Telegram, send `cd <path>` to switch a chat to another directory while keeping the current Codex session. Send `/new` to forget the current session, or `/new <path>` to start fresh in another directory.

Example:

```text
cd /media/debian/D/Prod/SytesLovki/
/new /media/debian/D/Prod/SytesLovki/
```

## Linux

Recommended setup:

```bash
uv venv --python python3.11 .venv
uv pip install -r requirements-voice.txt
python3 -m py_compile bot.py scripts/transcribe_voice.py
python3 bot.py
```

Install as a user-level systemd service:

```bash
scripts/linux/install_user_service.sh
```

Useful commands:

```bash
systemctl --user status telegram-codex-yolo-bot.service
journalctl --user -u telegram-codex-yolo-bot.service -n 80 --no-pager
systemctl --user restart telegram-codex-yolo-bot.service
```

Linux `.env` example:

```dotenv
CODEX_WORKDIR=/home/debian
STT_COMMAND=.venv/bin/python scripts/transcribe_voice.py
CODEX_COMMAND=codex exec --dangerously-bypass-approvals-and-sandbox --sandbox danger-full-access --skip-git-repo-check -C /home/debian -
CODEX_RESUME_COMMAND=codex exec resume --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check
```

## macOS

Recommended setup:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-voice.txt
python3 -m py_compile bot.py scripts/transcribe_voice.py
python3 bot.py
```

Install as a LaunchAgent:

```bash
scripts/macos/install_launch_agent.sh
```

Useful commands:

```bash
launchctl list | grep telegram-codex-yolo-bot
launchctl unload ~/Library/LaunchAgents/com.local.telegram-codex-yolo-bot.plist
launchctl load ~/Library/LaunchAgents/com.local.telegram-codex-yolo-bot.plist
```

macOS `.env` example:

```dotenv
CODEX_WORKDIR=/Users/you
STT_COMMAND=.venv/bin/python scripts/transcribe_voice.py
CODEX_COMMAND=codex exec --dangerously-bypass-approvals-and-sandbox --sandbox danger-full-access --skip-git-repo-check -C /Users/you -
CODEX_RESUME_COMMAND=codex exec resume --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check
```

## Windows

Run PowerShell from the repository directory.

Recommended setup:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe -m py_compile bot.py scripts\transcribe_voice.py
.\.venv\Scripts\python.exe bot.py
```

Install as a Scheduled Task that starts at logon:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install_scheduled_task.ps1
```

Useful commands:

```powershell
Get-ScheduledTask -TaskName telegram-codex-yolo-bot
Start-ScheduledTask -TaskName telegram-codex-yolo-bot
Stop-ScheduledTask -TaskName telegram-codex-yolo-bot
```

Windows `.env` example:

Use forward slashes in `.env` command paths on Windows. They are accepted by Windows tools and avoid shell escaping surprises.

```dotenv
CODEX_WORKDIR=C:/Users/you
STT_COMMAND=.venv/Scripts/python.exe scripts/transcribe_voice.py
CODEX_COMMAND=codex exec --dangerously-bypass-approvals-and-sandbox --sandbox danger-full-access --skip-git-repo-check -C C:/Users/you -
CODEX_RESUME_COMMAND=codex exec resume --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check
```

## Bot Commands

- `/start`, `/help` — help.
- `/status` — current task/session state.
- `/cancel` — stop the current Codex response, like Esc in the CLI.
- `pwd` or `/pwd` — show current Codex working directory.
- `cd <path>` or `/cd <path>` — switch working directory and keep the current Codex session.
- `/new [path]` — cancel any running task, forget the current session, and optionally switch directory.
- `/session` — show current Codex session id.
- `/resume <session_id>` — stop the current response and attach this chat to an existing Codex session.
- `/resume last` — stop the current response and attach to the latest Codex session.
- `/auto`, `/ru`, `/en`, `/uk` — voice transcription language.
- `/lang ru`, `/lang en` — bot interface language.
- `/about` — contact, Telegram channel, and GitHub links.
- `/reset` — forget current Codex session and local transcript.

## Data

Ignored runtime data:

- `.env`
- `.venv/`
- `state/`
- `state/settings/`
- `AGENTS.md`
- `PROJECT_INDEX.md`

Do not commit bot tokens, chat transcripts, downloaded media, model cache, local session ids, or local agent instruction files.
