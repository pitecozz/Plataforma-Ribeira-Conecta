#!/usr/bin/env bash
set -euo pipefail

# Configuration belongs in ~/.config/ribeira/backup-offhost.env (mode 600),
# never in Git.  The manifest is uploaded last by the transport.
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
backup_dir="${1:-$($repository_root/ops/backup/backup-runtime.sh)}"
PYTHONPATH="$repository_root/src" "$repository_root/.venv/bin/python" -m ribeira_platform.offhost_backup upload "$backup_dir"
