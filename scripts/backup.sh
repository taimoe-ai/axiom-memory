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
# Local dumps share a disk with the database, so for protection against
# disk loss each dump is also copied to Cloud Storage when the project's
# .env sets AXIOM_BACKUP_GCS_URI (e.g. gs://bucket/axiom/backups) and
# AXIOM_BACKUP_GCS_CREDENTIALS (a service-account key file with write
# access). Old objects there are not pruned: at ~1.5 MB a day the cost is
# negligible; add a bucket lifecycle rule if that changes.

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

# Read just these two keys; .env holds secrets and is not shell-safe to source.
env_value() {
    grep -E "^$1=" "$PROJECT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true
}
gcs_uri="${AXIOM_BACKUP_GCS_URI:-$(env_value AXIOM_BACKUP_GCS_URI)}"
gcs_credentials="${AXIOM_BACKUP_GCS_CREDENTIALS:-$(env_value AXIOM_BACKUP_GCS_CREDENTIALS)}"

if [[ -n "$gcs_uri" ]]; then
    CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$gcs_credentials" \
        gcloud storage cp "$target" "${gcs_uri%/}/$(basename "$target")" --quiet
    echo "$(date -u +%FT%TZ) offsite ok: ${gcs_uri%/}/$(basename "$target")"
fi
