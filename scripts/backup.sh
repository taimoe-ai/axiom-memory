#!/usr/bin/env bash
# Nightly logical backup of the Axiom database.
#
# Dumps through the running compose `db` service (the db port is not
# published), keeps the last RETAIN_DAYS dumps, and deletes older ones.
# Needs docker access, so install it in root's crontab, e.g.:
#
#   30 3 * * * /home/tim/axiom/scripts/backup.sh >> /var/log/axiom-backup.log 2>&1
#
# Restore into an empty database:
#   docker compose exec -T db pg_restore -U axiom -d axiom --clean < FILE.dump
#
# These dumps live on the same disk as the database; copy BACKUP_DIR
# off the machine for protection against disk loss.

set -euo pipefail

# cron runs with a minimal PATH; snap-installed docker lives in /snap/bin.
export PATH="$PATH:/usr/local/bin:/snap/bin"

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/axiom}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

target="$BACKUP_DIR/axiom-$(date -u +%Y%m%dT%H%M%SZ).dump"
partial="$target.partial"

# Custom format (-Fc) is compressed and restorable table by table. Write to
# a .partial name first so a failed dump never looks like a good backup.
docker compose --project-directory "$PROJECT_DIR" exec -T db \
    pg_dump -U axiom -d axiom -Fc > "$partial"
mv "$partial" "$target"

find "$BACKUP_DIR" -name 'axiom-*.dump' -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -name 'axiom-*.dump.partial' -mtime +1 -delete

echo "$(date -u +%FT%TZ) backup ok: $target ($(du -h "$target" | cut -f1))"
