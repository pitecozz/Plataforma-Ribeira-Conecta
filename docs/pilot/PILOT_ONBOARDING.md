# Pilot onboarding and secure access

`CLOUDFLARE_STATUS=AUTHORIZED_FOR_PILOT_ACCESS` authorizes only private-origin
HTTPS ingress. It does not authorize public PostgreSQL, metrics, debug routes,
development servers, broad firewall changes, automatic identity provisioning,
or committing pilot data/secrets.

The public hostname is `UNKNOWN` until supplied by the operator. Pilot records
stay outside Git and use tenant-scoped APIs, PostgreSQL RLS, audit, provenance
and Evidence First classifications.

## Target ingress

```text
pilot browser -> HTTPS Cloudflare -> named private tunnel
  -> 127.0.0.1:5173 static production frontend
  -> 127.0.0.1:8080 authenticated API only
PostgreSQL 127.0.0.1:55432, metrics 127.0.0.1:9109 and internal tooling stay private.
```

The frontend must be production/OIDC mode; Vite and development tokens are
prohibited. Cloudflare tunnel credentials/configuration are protected operator
files, never repository configuration.

## Operator prerequisites

1. Choose `https://<pilot-host>/` and create the Cloudflare tunnel/DNS in
   protected host configuration.
2. Register exact OIDC callback, logout URL and web origin:
   `https://<pilot-host>/`, `https://<pilot-host>/`, and
   `https://<pilot-host>`, respectively.
3. Configure issuer, audience, authorization/token/JWKS endpoints and public
   SPA client ID outside Git. No browser client secret.
4. Confirm the pilot user's issuer+subject before membership provisioning.

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
