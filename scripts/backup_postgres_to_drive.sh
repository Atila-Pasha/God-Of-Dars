#!/bin/sh
set -eu

project_dir=${GODOFDARS_PROJECT_DIR:-/opt/godofdars}
backup_root=${GODOFDARS_BACKUP_ROOT:-/opt/godofdars-backup/automated}
remote=${GODOFDARS_BACKUP_REMOTE:-gdrive_crypt:}

cd "$project_dir"

if [ ! -f .env ]; then
    echo "Missing production environment file: $project_dir/.env" >&2
    exit 1
fi
if ! command -v rclone >/dev/null 2>&1; then
    echo "rclone is not installed" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

install -d -m 700 "$backup_root"
pending_dir=$(mktemp -d "$backup_root/.pending.XXXXXX")
cleanup() {
    rm -rf -- "$pending_dir"
}
trap cleanup EXIT HUP INT TERM

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
bundle_name="godofdars-postgres-$timestamp"
bundle_dir="$pending_dir/$bundle_name"
upload_dir="$pending_dir/upload"
archive="$upload_dir/$bundle_name.tar.gz"

install -d -m 700 "$bundle_dir" "$upload_dir"

docker compose exec -T postgres \
    pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    > "$bundle_dir/database.dump"
docker compose exec -T postgres \
    pg_dumpall --globals-only -U "$POSTGRES_USER" \
    > "$bundle_dir/globals.sql"
docker compose exec -T postgres \
    pg_restore --list < "$bundle_dir/database.dump" \
    > "$bundle_dir/restore-list.txt"
docker compose exec -T postgres postgres --version \
    > "$bundle_dir/postgres-version.txt"
date -u --iso-8601=seconds > "$bundle_dir/created-at-utc.txt"

sha256sum "$bundle_dir/database.dump" "$bundle_dir/globals.sql" \
    > "$bundle_dir/SHA256SUMS"
tar -C "$pending_dir" -czf "$archive" "$bundle_name"
gzip -t "$archive"
sha256sum "$archive" > "$archive.sha256"
chmod -R go-rwx "$pending_dir"

# Upload and verify the new backup before removing any older remote backup.
rclone copy "$upload_dir" "$remote" --checksum
rclone check "$upload_dir" "$remote" --one-way

# A successful sync keeps exactly the newly verified archive and checksum.
rclone sync "$upload_dir" "$remote" --checksum --delete-after

install -d -m 700 "$backup_root/current"
rclone sync "$upload_dir" "$backup_root/current" --checksum --delete-after
chmod -R go-rwx "$backup_root/current"

echo "Backup completed: $bundle_name"
