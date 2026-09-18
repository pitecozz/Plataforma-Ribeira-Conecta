#!/usr/bin/env bash
set -euo pipefail

# The caller supplies the database URL through its process environment. This
# script never prints it and writes only the mode-600 user configuration file.
if [[ -z "${RIBEIRA_DATABASE_URL:-}" ]]; then
  echo "RIBEIRA_DATABASE_URL must be supplied through the environment" >&2
  exit 2
fi
runtime_environment="${RIBEIRA_ENV:-production}"
auth_mode="${RIBEIRA_AUTH_MODE:-oidc}"
repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
if [[ "$runtime_environment" == "development" && "$auth_mode" != "development" ]]; then
  echo "development runtime must use explicit development authentication" >&2
  exit 2
fi
if [[ "$runtime_environment" == "production" && "$auth_mode" != "oidc" ]]; then
  echo "production runtime requires OIDC authentication" >&2
  exit 2
fi
if [[ "$auth_mode" == "oidc" ]] && [[ -z "${RIBEIRA_JWT_ISSUER:-}" || -z "${RIBEIRA_JWT_AUDIENCE:-}" || -z "${RIBEIRA_JWT_JWKS_URL:-}" ]]; then
  echo "OIDC requires issuer, audience, and JWKS URL" >&2
  exit 2
fi
if [[ "$auth_mode" == "development" && -z "${RIBEIRA_DEV_AUTH_TOKEN:-}" ]]; then
  echo "development authentication requires RIBEIRA_DEV_AUTH_TOKEN" >&2
  exit 2
fi

config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/ribeira"
config_file="$config_dir/runtime.env"
mkdir -p "$config_dir"
chmod 700 "$config_dir"
umask 077
temporary_file="$(mktemp "$config_dir/.runtime.env.XXXXXX")"
trap 'rm -f "$temporary_file"' EXIT

{
  printf 'RIBEIRA_ENV=%s\n' "$runtime_environment"
  printf '%s\n' 'RIBEIRA_STORAGE=postgres'
  printf 'RIBEIRA_DATABASE_URL=%s\n' "$RIBEIRA_DATABASE_URL"
  printf 'RIBEIRA_OBJECT_STORAGE_ROOT=%s\n' "$repository_root/.local/object-storage"
  printf '%s\n' 'RIBEIRA_API_HOST=127.0.0.1'
  printf '%s\n' 'RIBEIRA_API_PORT=8080'
  printf '%s\n' 'RIBEIRA_CORS_ORIGINS=http://127.0.0.1:5173'
  printf 'RIBEIRA_AUTH_MODE=%s\n' "$auth_mode"
  if [[ "$auth_mode" == "development" ]]; then
    printf 'RIBEIRA_DEV_AUTH_TOKEN=%s\n' "$RIBEIRA_DEV_AUTH_TOKEN"
    printf '%s\n' 'RIBEIRA_DEV_AUTH_ROLES=PLATFORM_ADMIN'
  else
    printf 'RIBEIRA_JWT_ISSUER=%s\n' "$RIBEIRA_JWT_ISSUER"
    printf 'RIBEIRA_JWT_AUDIENCE=%s\n' "$RIBEIRA_JWT_AUDIENCE"
    printf 'RIBEIRA_JWT_JWKS_URL=%s\n' "$RIBEIRA_JWT_JWKS_URL"
    printf '%s\n' 'RIBEIRA_JWT_ALGORITHMS=RS256'
    printf '%s\n' 'RIBEIRA_JWKS_CACHE_TTL_SECONDS=300'
    printf '%s\n' 'RIBEIRA_JWKS_REFRESH_SECONDS=30'
    printf '%s\n' 'RIBEIRA_JWKS_TIMEOUT_SECONDS=3'
  fi
  printf '%s\n' 'RIBEIRA_GEOSPATIAL_WORKER_ID=ribeira-vps-01'
  printf '%s\n' 'RIBEIRA_GEOSPATIAL_STALE_AFTER_SECONDS=3600'
  printf '%s\n' 'RIBEIRA_GEOSPATIAL_MAX_ATTEMPTS=3'
} > "$temporary_file"
chmod 600 "$temporary_file"
mv -f "$temporary_file" "$config_file"
trap - EXIT
printf '%s\n' "wrote protected runtime configuration: $config_file"
