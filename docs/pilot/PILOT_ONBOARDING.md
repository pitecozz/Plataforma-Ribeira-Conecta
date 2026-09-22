# Pilot onboarding and secure access

`CLOUDFLARE_STATUS=AUTHORIZED_FOR_PILOT_ACCESS` authorizes only private-origin
HTTPS ingress. It does not authorize public PostgreSQL, metrics, debug routes,
development servers, broad firewall changes, automatic identity provisioning,
or committing pilot data/secrets.

`CLOUDFLARE_QUICK_TUNNEL=PILOT_TEST_ONLY` is the current access path. Its
`https://*.trycloudflare.com` hostname is assigned at runtime and is never
hardcoded into application behavior. Pilot records stay outside Git and use
tenant-scoped APIs, PostgreSQL RLS, audit, provenance and Evidence First
classifications. `https://app.ribeiraconecta.com.br` is
`FUTURE_CUSTOM_DOMAIN`, deferred until a domain is available.

## Target ingress

```text
pilot browser -> HTTPS Cloudflare Quick Tunnel
  -> 127.0.0.1:5173 static production frontend/private ingress
  -> /api/v1/* and /api/health/{live,ready} are stripped and proxied only to 127.0.0.1:8080
PostgreSQL 127.0.0.1:55432, metrics 127.0.0.1:9109 and internal tooling stay private.
```

The ingress allowlist deliberately returns `404` for `/metrics`,
`/api/metrics`, `/api/docs`, `/api/redoc` and `/api/openapi.json`; backend
diagnostics remain loopback-only.

The frontend must be production/OIDC mode; Vite and development tokens are
prohibited. Quick Tunnel does not use a tunnel credential. Its live process is
temporary: restarting it can assign a new public origin and requires OIDC,
frontend-build and API-CORS reconfiguration.

## Operator prerequisites

1. Start the Quick Tunnel command below and retain its exact assigned HTTPS
   origin for the remainder of the pilot session. It exposes one origin only:
   `http://127.0.0.1:5173`.
2. Register the exact assigned origin in Auth0: callback is `<origin>/`; web
   origin is `<origin>`. The SPA returns to `/`; it has no `/callback` route.
   The current SPA has no provider-logout implementation, so it has no
   functional Auth0 allowed-logout URL requirement. Do not add wildcard OIDC
   callback, logout or web-origin entries.
3. Configure the same exact origin in protected frontend build configuration
   (`VITE_RIBEIRA_PUBLIC_ORIGIN`) and API CORS (`RIBEIRA_CORS_ORIGINS`).
4. Configure issuer, audience, authorization/token/JWKS endpoints and public
   SPA client ID outside Git. No browser client secret.
5. Confirm the pilot user's issuer+subject before membership provisioning.

## Quick Tunnel operator procedure

1. Install `cloudflared` through the vendor-supported package source and verify
   its binary path.
2. Start the temporary tunnel without a token or credential:

   ```bash
   cloudflared tunnel --url http://127.0.0.1:5173
   ```

   Copy the assigned `https://…trycloudflare.com` origin exactly. Do not expose
   any other origin, open a firewall port, or add a wildcard OIDC entry.
3. In another protected operator shell, set that exact origin as
   `VITE_RIBEIRA_PUBLIC_ORIGIN` for the frontend build and
   `RIBEIRA_CORS_ORIGINS` for the API runtime configuration. Register the same
   exact origin with Auth0, then rebuild the frontend and restart only the API
   and static frontend during a controlled maintenance window.

   Always load the protected production/OIDC environment for a build that
   writes the live `frontend/dist`. A plain `npm run build` without those
   variables deliberately produces a fail-closed bundle and must not replace
   the active pilot artifact. After any validation build, rebuild with the
   protected environment before restarting the static service.

   Do not deploy the new ingress proxy against a development-auth API. First
   configure the protected runtime as `RIBEIRA_ENV=production` and
   `RIBEIRA_AUTH_MODE=oidc`, with its verified issuer, audience and JWKS
   configuration.

## Future custom domain

When a domain becomes available, `https://app.ribeiraconecta.com.br` can use
the named-tunnel templates in [the production runtime guide](../operations/PRODUCTION_RUNTIME_FOUNDATION.md#future-custom-domain-tunnel).
That migration changes public-origin, DNS, OIDC and CORS configuration only; it
does not change the loopback ingress or expose additional services.

## Audited onboarding

### First pilot workspace bootstrap

The initial tenant has a deliberate bootstrap dependency: normal tenant creation
requires a local platform administrator, while a tenant membership cannot exist
until its tenant exists. The host-only `pilot_bootstrap` command is the narrow
audited exception for a verified private import package. It is not an HTTP
endpoint, never creates a platform-admin identity, accepts only operator-owned
mode-`600` JSON files, validates the manifest/GeoJSON contract before a write,
uses deterministic IDs derived from both file checksums, and refuses partial or
mismatched retries.

Run its dry-run before any creation:

```bash
set -a; . ~/.config/ribeira/runtime.env; set +a
PYTHONPATH=src .venv/bin/python -m ribeira_platform.pilot_bootstrap \
  --manifest-file /absolute/private/import-manifest.json \
  --geojson-file /absolute/private/import.geojson --dry-run
```

After reviewing the proposed IDs, boundary classification, legal-boundary flag,
asset names and exclusions, repeat the same command without `--dry-run`. One
transaction creates the tenant, customer, property/boundary version, operational
customer-property link, approved assets and `PILOT_BOOTSTRAP_COMPLETED` audit
record. Existing complete deterministic imports return `EXISTS`; partial data
or changed file contents fail closed. The package source, checksums, boundary
usage and `legal_boundary_verified=false` remain in provenance/audit metadata.

The command does not provision an OIDC user. Only after its tenant exists may
the separate `identity_admin provision` workflow create the audited `VIEWER`
membership from the verified issuer and subject.

Use the same private inputs with `--verify` after creation to check the
persisted boundary, assets, bootstrap audit and a cross-tenant RLS denial. It
is read-only and does not require an OIDC identity.

### Tenant binding and audited onboarding gate

The current pilot SPA intentionally requires `VITE_RIBEIRA_TENANT_ID`. It is
not an OIDC-derived tenant selector: Farm360 API routes carry an explicit
tenant path, and the API verifies the OIDC identity's persisted membership for
that tenant. The current API does not provide a membership-discovery endpoint,
so the SPA must not infer a tenant from an arbitrary claim.

Runtime tenant, property and identity facts are operator-held state and are not
copied into Git. Existing external identity records without memberships do not
authorize pilot access. Do not set the frontend tenant value until an operator
has created or verified all of the following outside Git:

1. tenant and customer association;
2. pilot property with verified boundary, source and CRS;
3. verified initial assets and contextual evidence;
4. persisted tenant identifier for the protected frontend build input;
5. pilot user's verified OIDC issuer and subject; and
6. audited `VIEWER` membership through `identity_admin`.

The single tenant build binding is appropriate for this pilot. A future
multi-tenant selector requires a separately designed authenticated membership
discovery workflow; it must not replace this binding with a guessed token
claim.

1. Create tenant/customer association, property boundary/source/CRS, and only
   verified initial assets. A drawn/imported boundary is not legal title.
2. Build the frontend using final HTTPS API/OIDC configuration; confirm there
   is no `VITE_RIBEIRA_ACCESS_TOKEN` in the bundle.
3. Create an owner-only (`0600`) private request with verified issuer, subject,
   tenant ID, `VIEWER` role and operator actor. Run `identity_admin provision`
   with `--dry-run`, review, then provision. Claims never create membership.
4. Verify as the pilot user: Home, property, Farm360 map/assets/provenance,
   decisions/outcomes, report and feedback. Verify another tenant is denied.

Before go-live verify HTTPS, OIDC/JWKS, final-origin CORS, RLS/RBAC, journals,
no public Postgres/metrics/debug listener and full pilot E2E. To stop access,
disable the tunnel/hostname then revoke membership; never delete evidence/audit
records as rollback.

The public pre-authentication smoke is safe to run without customer
credentials. It checks exact HTTPS origin routing, API health, unauthenticated
tenant denial, PKCE parameters and root callback, the configured OIDC host and
that `/metrics` remains unavailable:

```bash
RIBEIRA_PLAYWRIGHT_BASE_URL='<exact-quick-tunnel-origin>' \
RIBEIRA_PLAYWRIGHT_OIDC_HOST='<issuer-hostname>' \
RIBEIRA_PLAYWRIGHT_TENANT_ID='<pilot-tenant-id>' \
npm --prefix frontend run e2e -- e2e/pilot-public-access.spec.ts
```

Run this through the repository-compatible official Playwright container when
the host lacks browser libraries. Passing this smoke does not prove user login
or authorized property access. The final customer journey still requires an
operator-controlled real Auth0 session; credentials, MFA material and browser
storage state must never be committed.
