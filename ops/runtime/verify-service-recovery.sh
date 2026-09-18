#!/usr/bin/env bash
set -euo pipefail

# A non-destructive service-recovery probe.  It intentionally does not enqueue
# a CDSE job: state-machine and stale-lease behaviour are exercised with
# explicitly classified doubles in the integration suite.  Run this with an
# empty queue, or while accepting that an already-claimed job may finish during
# the graceful worker restart.

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime_config="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira/runtime.env"

if [[ ! -r "$runtime_config" ]]; then
  echo "missing protected runtime configuration" >&2
  exit 2
fi

# shellcheck disable=SC1090
. "$runtime_config"
export RIBEIRA_DATABASE_URL RIBEIRA_OBJECT_STORAGE_ROOT
cd "$repository_root"

PYTHONPATH=src .venv/bin/python -m ribeira_platform.runtime_health all
systemctl --user restart ribeira-geospatial-worker.service
PYTHONPATH=src .venv/bin/python -m ribeira_platform.runtime_health worker --wait-seconds 30
systemctl --user restart ribeira-api.service
PYTHONPATH=src .venv/bin/python -m ribeira_platform.runtime_health api --wait-seconds 30
PYTHONPATH=src .venv/bin/python -m ribeira_platform.runtime_health all
printf '%s\n' 'controlled loopback service recovery verified'
