# Contributing

Thanks for helping improve Telegram Codex Yolo Bot.

This project is MIT licensed and open for practical improvements, bug reports, documentation fixes, and platform-specific install notes.

## Before You Start

- Do not include real Telegram bot tokens, user ids, chat logs, Codex session ids, downloaded media, or local `.env` contents.
- Keep changes small and easy to review.
- Prefer cross-platform behavior for Linux, macOS, Windows, and WSL.
- If a change affects setup, update `README.md` and `AI_INSTALLATION.md`.
- If a change affects bot commands, update the command list and Telegram command menu definitions.

## Local Checks

Run this before opening a pull request:

```bash
python3 -m py_compile bot.py bot_codex.py bot_media.py bot_i18n.py bot_telegram.py bot_state.py scripts/transcribe_voice.py
git diff --check
```

If you changed voice transcription, also verify `scripts/transcribe_voice.py` with a small local audio file when possible.

## Pull Requests

Good pull requests include:

- What changed.
- Why it changed.
- What was tested.
- Any OS-specific notes.

Keep secrets out of screenshots, logs, stack traces, and examples.

## Issues

For bugs, include:

- OS and version.
- Python version.
- How the bot is run: foreground, systemd user service, LaunchAgent, or Scheduled Task.
- Sanitized logs or error messages.
- Steps to reproduce.

For feature requests, describe the real workflow and the simplest behavior that would solve it.
