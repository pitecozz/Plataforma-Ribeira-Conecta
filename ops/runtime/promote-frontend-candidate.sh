#!/usr/bin/env bash
set -euo pipefail

# Promote an already validated candidate deliberately. It keeps the prior
# frontend artifact until private and public smoke checks pass, then rolls back
# automatically on failure. It never restarts Cloudflare, the API, workers or
# PostgreSQL.

if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 /absolute/path/to/candidate" >&2
  exit 2
fi

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
candidate_dir="$(CDPATH= cd -- "$1" && pwd)"
candidate_parent="$repository_root/.local/frontend-candidates"
live_dir="$repository_root/frontend/dist"
config_root="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira"
runtime_config="$config_root/runtime.env"
oidc_config="$config_root/oidc-validation.env"
frontend_config="$config_root/pilot-oidc-overrides.env"

case "$candidate_dir" in
  "$candidate_parent"/candidate.*) ;;
  *)
    echo "candidate must be a validated directory under $candidate_parent" >&2
    exit 2
    ;;
esac
if [[ ! -s "$candidate_dir/index.html" ]] || ! find "$candidate_dir/assets" -maxdepth 1 -type f -name 'maplibre-gl-worker-*.js' -print -quit | grep -q . || ! grep -q '"state":"VALIDATED"' "$candidate_dir/.ribeira-candidate.json"; then
  echo "candidate artifact is incomplete" >&2
  exit 2
fi
for protected_config in "$runtime_config" "$oidc_config" "$frontend_config"; do
  if [[ ! -r "$protected_config" ]]; then
    echo "required protected runtime configuration is unavailable" >&2
    exit 2
  fi
done

set -a
# shellcheck disable=SC1090
. "$runtime_config"
# shellcheck disable=SC1090
. "$oidc_config"
# shellcheck disable=SC1090
. "$frontend_config"
set +a
if [[ "${RIBEIRA_ENV:-}" != "production" || "${RIBEIRA_AUTH_MODE:-}" != "oidc" || -z "${VITE_RIBEIRA_PUBLIC_ORIGIN:-}" ]]; then
  echo "promotion requires protected production/OIDC configuration" >&2
  exit 2
fi
required=(
  VITE_RIBEIRA_PUBLIC_ORIGIN
  VITE_RIBEIRA_TENANT_ID
  VITE_RIBEIRA_AUTH_MODE
  VITE_RIBEIRA_OIDC_AUDIENCE
  VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT
  VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT
  VITE_RIBEIRA_OIDC_CLIENT_ID
)
candidate_bundle="$(find "$candidate_dir/assets" -maxdepth 1 -type f -name 'index-*.js' -print -quit)"
for variable_name in "${required[@]}"; do
  if [[ -z "${!variable_name:-}" ]] || ! grep -Fq "${!variable_name}" "$candidate_bundle"; then
    echo "candidate application configuration smoke failed" >&2
    exit 2
  fi
done

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$repository_root/.local/frontend-previous-$timestamp"
promoted=0
rollback() {
  if [[ "$promoted" -eq 1 && -d "$backup_dir" ]]; then
    rm -rf -- "$live_dir"
    mv -- "$backup_dir" "$live_dir"
    systemctl --user restart ribeira-frontend
    echo "promotion failed; restored the prior frontend artifact" >&2
  fi
}
trap rollback ERR

if [[ ! -d "$live_dir" ]]; then
  echo "known-good frontend artifact is unavailable" >&2
  exit 2
fi
mv -- "$live_dir" "$backup_dir"
mv -- "$candidate_dir" "$live_dir"
promoted=1
systemctl --user restart ribeira-frontend
curl --fail --silent --show-error http://127.0.0.1:5173/health/ready >/dev/null
curl --fail --silent --show-error "${VITE_RIBEIRA_PUBLIC_ORIGIN%/}/" >/dev/null
curl --fail --silent --show-error "${VITE_RIBEIRA_PUBLIC_ORIGIN%/}/api/health/ready" >/dev/null
live_bundle="$(find "$live_dir/assets" -maxdepth 1 -type f -name 'index-*.js' -print -quit)"
for variable_name in "${required[@]}"; do
  if ! grep -Fq "${!variable_name}" "$live_bundle"; then
    echo "promoted frontend application configuration smoke failed" >&2
    false
  fi
done
worker_path="/assets/$(find "$live_dir/assets" -maxdepth 1 -type f -name 'maplibre-gl-worker-*.js' -printf '%f' -quit)"
worker_headers="$(curl --fail --silent --show-error --head "${VITE_RIBEIRA_PUBLIC_ORIGIN%/}$worker_path")"
if ! grep -qi '^content-type:.*javascript' <<<"$worker_headers"; then
  echo "promoted MapLibre worker has an invalid MIME type" >&2
  false
fi

rm -rf -- "$backup_dir"
promoted=0
trap - ERR
printf 'FRONTEND_PROMOTION=PASS\n'
