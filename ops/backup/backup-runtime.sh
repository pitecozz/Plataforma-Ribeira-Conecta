#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime_config="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira/runtime.env"
object_root="${RIBEIRA_OBJECT_STORAGE_ROOT:-}"
if [[ -z "$object_root" && -r "$runtime_config" ]]; then
  # Only this nonsecret setting is read; database and provider credentials are
  # never parsed, logged, or included in the backup.
  object_root="$(sed -n 's/^RIBEIRA_OBJECT_STORAGE_ROOT=//p' "$runtime_config")"
fi
backup_root="${RIBEIRA_BACKUP_ROOT:-$HOME/.local/share/ribeira/backups}"
database_name="${RIBEIRA_BACKUP_DB_NAME:-ribeira_dev}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$backup_root/$stamp"

if [[ -z "$object_root" || ! -d "$object_root" ]]; then
  echo "object storage root is unavailable" >&2
  exit 2
fi
umask 077
install -d -m 700 "$destination"
temporary_dump="$destination/postgres.dump.partial"
trap 'rm -f "$temporary_dump"' EXIT

docker compose -f "$repository_root/docker-compose.yml" exec -T postgres \
  pg_dump -U ribeira_admin -d "$database_name" -Fc --no-owner --no-privileges > "$temporary_dump"
mv -f "$temporary_dump" "$destination/postgres.dump"
tar --create --file "$destination/object-storage.tar" --directory "$object_root" .
cp "$repository_root/ops/runtime/runtime.env.example" "$destination/runtime.env.example"
(cd "$destination" && sha256sum postgres.dump object-storage.tar runtime.env.example > SHA256SUMS)
chmod 600 "$destination"/*
printf '%s\n' "$destination"
