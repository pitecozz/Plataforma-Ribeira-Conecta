# Pilot onboarding and secure access

`CLOUDFLARE_STATUS=AUTHORIZED_FOR_PILOT_ACCESS` authorizes only private-origin
HTTPS ingress. It does not authorize public PostgreSQL, metrics, debug routes,
development servers, broad firewall changes, automatic identity provisioning,
or committing pilot data/secrets.

The authorized public hostname is `https://app.ribeiraconecta.com.br`. Pilot records
stay outside Git and use tenant-scoped APIs, PostgreSQL RLS, audit, provenance
and Evidence First classifications.

## Target ingress

```text
pilot browser -> HTTPS Cloudflare -> named private tunnel
  -> 127.0.0.1:5173 static production frontend/private ingress
  -> /api is stripped and proxied only to 127.0.0.1:8080
PostgreSQL 127.0.0.1:55432, metrics 127.0.0.1:9109 and internal tooling stay private.
```

The frontend must be production/OIDC mode; Vite and development tokens are
prohibited. Cloudflare tunnel credentials/configuration are protected operator
files, never repository configuration.

## Operator prerequisites

1. Create the named Cloudflare tunnel/DNS for `app.ribeiraconecta.com.br` in protected
   host configuration. The tunnel exposes one origin only:
   `http://127.0.0.1:5173`; its catch-all route is `http_status:404`.
2. Register the exact OIDC callback URL and web origin:
   `https://app.ribeiraconecta.com.br/` and `https://app.ribeiraconecta.com.br`,
   respectively. The SPA returns to `/`; it has no `/callback` route. The
   current SPA has no provider-logout implementation, so it has no functional
   Auth0 allowed-logout URL requirement. If an operator later enables Auth0
   logout, its approved return URL must be `https://app.ribeiraconecta.com.br/` and
   the user workflow/docs must be updated in the same milestone.
3. Configure issuer, audience, authorization/token/JWKS endpoints and public
   SPA client ID outside Git. No browser client secret.
4. Confirm the pilot user's issuer+subject before membership provisioning.

## Cloudflare operator procedure

1. Install `cloudflared` through the vendor-supported package source and verify
   its binary path. Do not use a quick tunnel.
2. Create a named tunnel and route `app.ribeiraconecta.com.br` to it in Cloudflare.
   Keep the generated credential JSON in
   `~/.config/cloudflared/` with mode `0600`; do not put its contents or a token
   in Git, shell history, service arguments, or chat.
3. Create `~/.config/ribeira/cloudflared-pilot.yml` from the nonsecret template
   in [the production runtime guide](../operations/PRODUCTION_RUNTIME_FOUNDATION.md#cloudflare-pilot-tunnel-operator-held-configuration),
   again with mode `0600`.
4. After the credential file and tunnel UUID exist, install the nonsecret
   templates as protected local files, replace their two UUID placeholders, and
   enable the user service:

   ```bash
   install -d -m 700 ~/.config/ribeira ~/.config/cloudflared ~/.config/systemd/user
   install -m 600 ops/runtime/cloudflared-pilot.yml.example ~/.config/ribeira/cloudflared-pilot.yml
   install -m 644 ops/systemd/user/ribeira-cloudflared-pilot.service.example ~/.config/systemd/user/ribeira-cloudflared-pilot.service
   systemctl --user daemon-reload
   systemctl --user enable --now ribeira-cloudflared-pilot.service
   journalctl --user -u ribeira-cloudflared-pilot.service -f
   ```

   Do not run the service before replacing the placeholders in the protected
   configuration. Its only origin is the static ingress at `127.0.0.1:5173`;
   the catch-all is 404.
5. Rebuild the frontend using protected OIDC configuration based on
   `ops/runtime/pilot-frontend.env.example`, update the protected API CORS
   origin to `https://app.ribeiraconecta.com.br`, then restart only the static frontend
   and API during a controlled maintenance window.

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
