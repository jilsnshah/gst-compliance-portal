#!/usr/bin/env bash
# Restores a backup over the current data. Destructive on purpose.
#
#   ./restore.sh backups/nhs-2026-08-12-2115.tar.gz

set -euo pipefail
cd "$(dirname "$0")"
ARCHIVE="${1:?usage: ./restore.sh <archive.tar.gz>}"
[ -f "$ARCHIVE" ] || { echo "no such archive: $ARCHIVE" >&2; exit 1; }

echo "This replaces everything in ./data with the contents of $ARCHIVE."
read -r -p "Type RESTORE to continue: " confirm
[ "$confirm" = "RESTORE" ] || { echo "cancelled"; exit 1; }

docker compose down
mv ./data "./data.before-restore-$(date +%s)"
mkdir -p ./data
tar -xzf "$ARCHIVE" -C ./data
mv ./data/.backup.db ./data/gst_platform.db
docker compose up -d --build
echo "restored. The previous data is kept alongside as data.before-restore-*"
