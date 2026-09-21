#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
unit_source="$repository_root/ops/systemd/user"
unit_target="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
runtime_config="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira/runtime.env"

if [[ ! -f "$runtime_config" ]]; then
  echo "missing protected runtime configuration: $runtime_config" >&2
  exit 2
fi
if [[ "$(stat -c '%a' "$runtime_config")" != "600" ]]; then
  echo "runtime configuration must have mode 600" >&2
  exit 2
fi
if [[ ! -f "${XDG_CONFIG_HOME:-$HOME/.config}/ribeira/cdse.env" ]]; then
  echo "missing protected CDSE configuration" >&2
  exit 2
fi

install -d -m 700 "$unit_target"
install -m 644 "$unit_source"/ribeira-*.service "$unit_target/"
install -m 644 "$unit_source"/ribeira-*.timer "$unit_target/"
systemctl --user daemon-reload
systemctl --user enable ribeira-api.service ribeira-geospatial-worker.service ribeira-frontend.service ribeira-wis2-reconcile.timer
printf '%s\n' 'installed and enabled user services and WIS2 timer; use systemctl --user start ribeira-api ribeira-geospatial-worker ribeira-frontend'
if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" != "yes" ]]; then
  printf '%s\n' 'WARNING: user lingering is disabled; enable it before relying on reboot persistence.' >&2
fi
