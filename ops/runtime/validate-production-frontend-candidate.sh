#!/usr/bin/env bash
set -euo pipefail

# Build an OIDC frontend candidate without replacing frontend/dist. This script
# is deliberately separate from promotion: a passing candidate is necessary,
# but never by itself authorizes a public release.

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
config_root="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira"
runtime_config="$config_root/runtime.env"
oidc_config="$config_root/oidc-validation.env"
frontend_config="$config_root/pilot-oidc-overrides.env"

for protected_config in "$runtime_config" "$oidc_config" "$frontend_config"; do
  if [[ ! -r "$protected_config" ]]; then
    echo "required protected frontend configuration is unavailable" >&2
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

if [[ "${RIBEIRA_ENV:-}" != "production" || "${RIBEIRA_AUTH_MODE:-}" != "oidc" ]]; then
  echo "candidate validation requires protected production OIDC runtime" >&2
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
missing=0
for variable_name in "${required[@]}"; do
  if [[ -n "${!variable_name:-}" ]]; then
    printf '%s=PRESENT\n' "$variable_name"
  else
    printf '%s=MISSING\n' "$variable_name" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  exit 2
fi
if [[ -n "${VITE_RIBEIRA_ACCESS_TOKEN:-}" ]]; then
  echo "candidate validation refuses a browser access token" >&2
  exit 2
fi

candidate_parent="${RIBEIRA_FRONTEND_CANDIDATE_PARENT:-$repository_root/.local/frontend-candidates}"
mkdir -p "$candidate_parent"
chmod 700 "$candidate_parent"
candidate_dir="$(mktemp -d "$candidate_parent/candidate.XXXXXX")"

cleanup_candidate=1
cleanup() {
  if [[ "$cleanup_candidate" -eq 1 ]]; then
    rm -rf -- "$candidate_dir"
  fi
}
trap cleanup EXIT

(
  cd "$repository_root/frontend"
  node scripts/verify-production-config.mjs >/dev/null
  npm run typecheck
  npm run lint
  npm run test
  ./node_modules/.bin/vite build --outDir "$candidate_dir"
)

if [[ ! -s "$candidate_dir/index.html" ]]; then
  echo "candidate index was not emitted" >&2
  exit 1
fi
worker_file="$(find "$candidate_dir/assets" -maxdepth 1 -type f -name 'maplibre-gl-worker-*.js' -print -quit)"
if [[ -z "$worker_file" || ! -s "$worker_file" ]]; then
  echo "candidate MapLibre worker was not emitted" >&2
  exit 1
fi
main_bundle="$(find "$candidate_dir/assets" -maxdepth 1 -type f -name 'index-*.js' -print -quit)"
if [[ -z "$main_bundle" || ! -s "$main_bundle" ]]; then
  echo "candidate application bundle was not emitted" >&2
  exit 1
fi
for variable_name in "${required[@]}"; do
  if ! grep -Fq "${!variable_name}" "$main_bundle"; then
    printf '%s=NOT_EMBEDDED\n' "$variable_name" >&2
    echo "candidate does not contain required protected build configuration" >&2
    exit 1
  fi
done
printf 'APPLICATION_CONFIG_SMOKE=PASS\n'

candidate_port="$($repository_root/.venv/bin/python - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
"$repository_root/.venv/bin/python" -m http.server "$candidate_port" \
  --bind 127.0.0.1 --directory "$candidate_dir" >/dev/null 2>&1 &
preview_pid=$!
stop_preview() {
  kill "$preview_pid" 2>/dev/null || true
  wait "$preview_pid" 2>/dev/null || true
}
trap 'stop_preview; cleanup' EXIT

for attempt in $(seq 1 20); do
  if curl --fail --silent "http://127.0.0.1:$candidate_port/" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 20 ]]; then
    echo "candidate loopback smoke did not become ready" >&2
    exit 1
  fi
  sleep 0.25
done
playwright_log="$(mktemp "$candidate_parent/playwright.XXXXXX")"
if ! (
  cd "$repository_root/frontend"
  RIBEIRA_PLAYWRIGHT_BASE_URL="http://127.0.0.1:$candidate_port" \
    ./node_modules/.bin/playwright test e2e/production-bootstrap.spec.ts
) >"$playwright_log" 2>&1; then
  if grep -q "Host system is missing dependencies to run browsers" "$playwright_log"; then
    printf 'APPLICATION_BROWSER_SMOKE=BLOCKED_BROWSER_DEPENDENCIES\n'
  else
    cat "$playwright_log" >&2
    rm -f -- "$playwright_log"
    exit 1
  fi
else
  printf 'APPLICATION_BROWSER_SMOKE=PASS\n'
fi
rm -f -- "$playwright_log"
worker_relative="assets/$(basename -- "$worker_file")"
worker_headers="$(curl --fail --silent --show-error --head "http://127.0.0.1:$candidate_port/$worker_relative")"
if ! grep -qi '^content-type:.*javascript' <<<"$worker_headers"; then
  echo "candidate MapLibre worker has an invalid MIME type" >&2
  exit 1
fi

stop_preview
trap cleanup EXIT
cleanup_candidate=0
trap - EXIT
source_revision="$(git -C "$repository_root" rev-parse HEAD)"
printf '{"state":"VALIDATED","source_revision":"%s","maplibre_worker":"%s"}\n' \
  "$source_revision" "$worker_relative" > "$candidate_dir/.ribeira-candidate.json"
printf 'CANDIDATE_DIR=%s\n' "$candidate_dir"
printf 'CANDIDATE_SMOKE=PASS\n'
printf 'MAPLIBRE_WORKER=%s\n' "$worker_relative"
