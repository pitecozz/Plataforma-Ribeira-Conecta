#!/usr/bin/env bash
set -euo pipefail

# This creates a loopback-only *development validation* build. It is
# intentionally impossible in production, where OIDC browser configuration is
# required and a development bearer token must never be compiled into assets.
repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime_config="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira/runtime.env"
if [[ ! -r "$runtime_config" ]]; then
  echo "protected runtime configuration is unavailable" >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
. "$runtime_config"
set +a
if [[ "${RIBEIRA_ENV:-}" != "development" || "${RIBEIRA_AUTH_MODE:-}" != "development" || -z "${RIBEIRA_DEV_AUTH_TOKEN:-}" ]]; then
  echo "validation frontend build requires explicit development authentication" >&2
  exit 2
fi
read -r validation_tenant validation_property < <(
  docker compose -f "$repository_root/docker-compose.yml" exec -T postgres \
    psql -U ribeira_admin -d ribeira_dev -At -F ' ' -c \
    "SELECT p.tenant_id, p.id FROM property p JOIN derived_product d ON d.tenant_id=p.tenant_id AND d.property_id=p.id WHERE d.output_reference IS NOT NULL ORDER BY d.created_at LIMIT 1"
)
if [[ -z "${validation_tenant:-}" || -z "${validation_property:-}" ]]; then
  echo "real validation property with a persisted product is unavailable" >&2
  exit 1
fi
(
  cd "$repository_root/frontend"
  VITE_RIBEIRA_AUTH_MODE=development \
  VITE_RIBEIRA_API_URL="http://127.0.0.1:${RIBEIRA_API_PORT:-8080}" \
  VITE_RIBEIRA_TENANT_ID="$validation_tenant" \
  VITE_RIBEIRA_PROPERTY_ID="$validation_property" \
  VITE_RIBEIRA_ACCESS_TOKEN="$RIBEIRA_DEV_AUTH_TOKEN" \
  npm run build
)
printf '%s\n' "built loopback development validation frontend"
