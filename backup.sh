#!/usr/bin/env bash
# Backs up the whole record: the database and every uploaded document.
#
#   ./backup.sh                  -> ./backups/nhs-YYYY-MM-DD-HHMM.tar.gz
#   ./backup.sh /mnt/nas/gst     -> writes there instead
#
# Nightly, via the server's crontab:
#   15 21 * * *  cd /opt/nhs_sol && ./backup.sh >> backups/backup.log 2>&1
#
# Keep a copy OFF this machine. A backup on the same disk does not survive the
# disk failing.

set -euo pipefail
cd "$(dirname "$0")"

DEST="${1:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d-%H%M)"
OUT="$DEST/nhs-$STAMP.tar.gz"

mkdir -p "$DEST"
[ -d ./data ] || { echo "no ./data directory -- is this the right server?" >&2; exit 1; }

# SQLite is mid-write at any moment, so copy through its own backup API rather
# than tarring the live file, which can capture a torn database.
if docker compose ps --status running --services 2>/dev/null | grep -qx api; then
  docker compose exec -T api python -c "
import sqlite3, os
src = sqlite3.connect('/data/gst_platform.db')
dst = sqlite3.connect('/data/.backup.db')
src.backup(dst); dst.close(); src.close()
" || { echo 'consistent snapshot failed' >&2; exit 1; }
  SNAP=".backup.db"
else
  echo "api container not running -- copying the file directly"
  cp ./data/gst_platform.db ./data/.backup.db
  SNAP=".backup.db"
fi

tar -czf "$OUT" -C ./data "$SNAP" storage
rm -f ./data/.backup.db

echo "$(date '+%F %T')  wrote $OUT ($(du -h "$OUT" | cut -f1))"

# Prune old archives, but never the only one left.
find "$DEST" -name 'nhs-*.tar.gz' -type f -mtime "+$KEEP_DAYS" -print -delete 2>/dev/null || true
