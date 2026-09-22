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
  -> /api is stripped and proxied only to 127.0.0.1:8080
PostgreSQL 127.0.0.1:55432, metrics 127.0.0.1:9109 and internal tooling stay private.
```

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

## Future custom domain

When a domain becomes available, `https://app.ribeiraconecta.com.br` can use
the named-tunnel templates in [the production runtime guide](../operations/PRODUCTION_RUNTIME_FOUNDATION.md#future-custom-domain-tunnel).
That migration changes public-origin, DNS, OIDC and CORS configuration only; it
does not change the loopback ingress or expose additional services.

## Audited onboarding

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
