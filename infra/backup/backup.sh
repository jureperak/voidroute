#!/usr/bin/env bash
# Nightly encrypted backup of voidroute configuration (not media) with restic.
# Reads its settings from ~/.config/voidroute-backup.env (see backup.env.example).
set -euo pipefail

ENV_FILE="${VOIDROUTE_BACKUP_ENV:-$HOME/.config/voidroute-backup.env}"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 1; }
set -a
. "$ENV_FILE"
set +a

: "${MEDIA_ROOT:?MEDIA_ROOT is not set}"
: "${SERVER_BASE_PATH:?SERVER_BASE_PATH is not set}"
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is not set}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is not set}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

VW_DIR="$SERVER_BASE_PATH/vaultwarden/data"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Consistent copy of the live Vaultwarden database, safe while the container runs.
# The raw db.sqlite3 is excluded below, so only this copy is stored.
if [ -f "$VW_DIR/db.sqlite3" ]; then
  python3 -c 'import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
    "$VW_DIR/db.sqlite3" "$STAGE/db.sqlite3"
fi

restic backup \
  --tag voidroute-config \
  --exclude "$MEDIA_ROOT/config/*/logs" \
  --exclude "$MEDIA_ROOT/config/*/Cache" \
  --exclude "$MEDIA_ROOT/config/*/cache" \
  --exclude "$MEDIA_ROOT/config/jellyfin/data/metadata" \
  --exclude "$MEDIA_ROOT/config/jellyfin/transcodes" \
  --exclude "$VW_DIR/db.sqlite3*" \
  "$MEDIA_ROOT/config" \
  "$SERVER_BASE_PATH/caddy/data" \
  "$SERVER_BASE_PATH/portainer/data" \
  "$VW_DIR" \
  "$SERVER_BASE_PATH/opengym/data" \
  "$SERVER_BASE_PATH/vikunja" \
  "$STAGE"

restic forget --tag voidroute-config --keep-daily 7 --keep-weekly 4 --prune
