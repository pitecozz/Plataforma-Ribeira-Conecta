#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /path/to/backup-directory" >&2
  exit 2
fi
backup_dir="$(realpath "$1")"
archive="$backup_dir/postgres.dump"
checksums="$backup_dir/SHA256SUMS"
if [[ ! -f "$archive" || ! -f "$checksums" ]]; then
  echo "backup archive or checksum manifest is missing" >&2
  exit 2
fi
(cd "$backup_dir" && sha256sum --check SHA256SUMS)
object_manifest="$(mktemp)"
object_restore_root="$(mktemp -d)"
tar --list --file "$backup_dir/object-storage.tar" > "$object_manifest"
tar --extract --file "$backup_dir/object-storage.tar" --directory "$object_restore_root"

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
database_name="${RIBEIRA_BACKUP_DB_NAME:-ribeira_dev}"
restore_database="ribeira_restore_verify_$(date -u +%Y%m%d%H%M%S)"
cleanup() {
  rm -f "$object_manifest"
  rm -rf "$object_restore_root"
  docker compose -f "$repository_root/docker-compose.yml" exec -T postgres \
    dropdb -U ribeira_admin --if-exists "$restore_database" >/dev/null 2>&1 || true
}
trap cleanup EXIT

source_versions="$(docker compose -f "$repository_root/docker-compose.yml" exec -T postgres psql -U ribeira_admin -d "$database_name" -Atc 'SELECT count(*) FROM schema_migrations')"
docker compose -f "$repository_root/docker-compose.yml" exec -T postgres \
  createdb -U ribeira_admin "$restore_database"
cat "$archive" | docker compose -f "$repository_root/docker-compose.yml" exec -T postgres \
  pg_restore -U ribeira_admin -d "$restore_database" --no-owner --no-privileges
restored_versions="$(docker compose -f "$repository_root/docker-compose.yml" exec -T postgres psql -U ribeira_admin -d "$restore_database" -Atc 'SELECT count(*) FROM schema_migrations')"
if [[ "$source_versions" != "$restored_versions" ]]; then
  echo "restore verification failed: migration count differs" >&2
  exit 1
fi
# A database restore alone does not prove that its persisted COG references are
# in the object archive. Check every non-null local derived-product reference.
while IFS=$'\t' read -r reference expected_checksum; do
  [[ -z "$reference" ]] && continue
  if [[ "$reference" != local://* ]] || ! grep -Fqx "./${reference#local://}" "$object_manifest"; then
    echo "restore verification failed: a derived-product object is absent" >&2
    exit 1
  fi
  object_path="$object_restore_root/${reference#local://}"
  if [[ -n "$expected_checksum" && "$(sha256sum "$object_path" | awk '{print $1}')" != "$expected_checksum" ]]; then
    echo "restore verification failed: a derived-product object checksum differs" >&2
    exit 1
  fi
done < <(docker compose -f "$repository_root/docker-compose.yml" exec -T postgres \
  psql -U ribeira_admin -d "$restore_database" -Atc \
  "SELECT output_reference || E'\\t' || coalesce(output_checksum, '') FROM derived_product WHERE output_reference IS NOT NULL")
printf '%s\n' "controlled restore verified: $restore_database"
