#!/usr/bin/env bash
# One-time setup: installs a systemd timer that runs backup.sh every night at 03:00
# as the current user. Run on the server with: sudo bash infra/backup/install-timer.sh
# (run it with sudo from your own user account, not as root directly)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN_AS="${SUDO_USER:-$(id -un)}"

sudo tee /etc/systemd/system/voidroute-backup.service >/dev/null <<UNIT
[Unit]
Description=voidroute configuration backup
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$RUN_AS
ExecStart=/usr/bin/env bash $REPO/infra/backup/backup.sh
UNIT

sudo tee /etc/systemd/system/voidroute-backup.timer >/dev/null <<UNIT
[Unit]
Description=Nightly voidroute configuration backup

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now voidroute-backup.timer
systemctl list-timers voidroute-backup.timer --no-pager
