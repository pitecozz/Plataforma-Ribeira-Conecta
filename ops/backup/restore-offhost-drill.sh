#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 BACKUP_ID" >&2
  exit 2
fi
config_file="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira/backup-offhost.env"
if [[ ! -r "$config_file" ]]; then
  echo "protected off-host backup configuration is unavailable" >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
. "$config_file"
set +a
repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT
PYTHONPATH="$repository_root/src" "$repository_root/.venv/bin/python" -m ribeira_platform.offhost_backup download "$1" "$temporary_root/backup"
"$repository_root/ops/backup/verify-backup-restore.sh" "$temporary_root/backup"
