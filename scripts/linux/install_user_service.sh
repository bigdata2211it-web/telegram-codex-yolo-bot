#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="telegram-codex-yolo-bot.service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_PATH="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

mkdir -p "${SYSTEMD_USER_DIR}"
cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=Telegram bridge for Codex high-autonomy exec
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=/usr/bin/python3 ${ROOT_DIR}/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}"
systemctl --user --no-pager --full status "${SERVICE_NAME}"
