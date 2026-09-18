# Production identity and disaster recovery

This foundation remains private and loopback-only. It neither authorizes a public listener nor changes SSH, UFW, PostgreSQL publishing, or worker exposure.

## Identity architecture

Authentication, authorization, and membership are separate controls:

```text
OIDC JWT (signature, issuer, audience, exp, nbf, sub)
  -> issuer + subject identity_user
  -> active tenant_membership + local iam_role
  -> selected tenant context -> PostgreSQL RLS
```

`issuer + subject` is the stable external identity key. Email is display data, not an identity key. A JWT claim cannot assign a Ribeira tenant, role, or platform administrator privilege. `platform_admin` is a persisted local attribute; membership is a persisted, status-bearing record. Legacy identities with no issuer remain deliberately unmapped until a controlled operator workflow assigns them.

In `production`, `RIBEIRA_AUTH_MODE=oidc` is mandatory. The process refuses a development token, missing issuer/audience/JWKS configuration, or unsupported algorithm. Development/test retain the explicit development provider only.

The resource server allows only configured asymmetric algorithms. It validates JWTs cryptographically and verifies `iss`, `aud`, `exp`, `nbf`, and `sub`; decoded-but-unverified claims have no authority. JWKS has bounded timeout, `kid` rotation refresh, and bounded cache TTL. A temporary IdP outage is degraded dependency state: cached valid keys work only until TTL; missing/unknown keys fail closed with 401. API liveness does not depend on an IdP request.

The SPA uses Authorization Code with PKCE (`S256`), never implicit flow. Its public client ID/endpoints can be build configuration; no browser client secret is allowed. Access tokens are memory-only. PKCE verifier/state are short-lived `sessionStorage` values solely for redirect validation; no refresh token is persisted in localStorage. The browser does not authorize by decoding tokens and it never logs them.

The current private validation runtime is explicitly development-only. Rebuild
its loopback Farm 360 static bundle with `ops/runtime/build-validation-frontend.sh`.
That script refuses production mode and selects an existing persisted validation
property; its ephemeral development bearer token is intentionally compiled only
into the private validation build. A production build must use `VITE_RIBEIRA_AUTH_MODE=oidc` plus public OIDC endpoint/client-ID configuration and must not contain `VITE_RIBEIRA_ACCESS_TOKEN`.

Before use, provision an OIDC application with exact loopback redirect URI, issuer, audience, authorization endpoint, token endpoint, JWKS endpoint, and public SPA client ID. Auth0, Keycloak, Entra ID, Cognito, and other standard providers are compatible; no provider is selected by this repository. Registration of an `identity_user` and `tenant_membership` is a separately audited operator action—claims never auto-provision access.

## Auth audit and response semantics

Structured journals record authentication success/failure and authorization/membership denial with request/correlation ID, tenant where relevant, status, and sanitized failure code. Never add JWTs, authorization headers, client secrets, or provider credentials to fields. Invalid signatures, issuer, audience, validity period, or unknown `kid` return 401. A valid identity with no local membership returns 403; RLS protects data after authorization.

## Off-host backup architecture

Local artifact creation remains:

```bash
backup_dir="$(ops/backup/backup-runtime.sh)"
ops/backup/verify-backup-restore.sh "$backup_dir"
```

It contains PostgreSQL custom dump, object-storage archive, checksums, migration state, and nonsecret runtime example. It excludes protected runtime/CDSE/SSH/token files. Verification restores objects into a temporary directory, checks each persisted local derived-product reference and output SHA-256, restores PostgreSQL only into a temporary database, and drops it after verification.

The remote transport is a small S3-compatible adapter. This supports AWS S3, Cloudflare R2, Backblaze B2 S3 API, or another compatible service without changing backup format. Selection must use actual region, lifecycle/versioning, durability, encryption, egress, and cost evidence—not brand preference. Those values are `UNKNOWN`: no authorized remote destination was supplied. The manifest uploads last; an interrupted upload with no final manifest is never restorable.

Create protected unversioned `~/.config/ribeira/backup-offhost.env` (mode 600), with only endpoint/region/bucket/prefix and the provider's server-side credential chain. Never put it in Git or backup. Example names:

```bash
RIBEIRA_BACKUP_S3_BUCKET=operator-provisioned-private-bucket
RIBEIRA_BACKUP_S3_PREFIX=ribeira-backups
RIBEIRA_BACKUP_S3_ENDPOINT_URL=https://operator-provisioned-endpoint
RIBEIRA_BACKUP_S3_REGION=operator-provisioned-region
```

After the operator provides a bucket:

```bash
backup_id="$(ops/backup/upload-offhost-backup.sh)"
ops/backup/restore-offhost-drill.sh "$backup_id"
```

The drill downloads, verifies manifest/SHA-256, restores database/object archive to temporary targets, validates migrations, persisted COG checksum, product/provenance references, and RLS through the PostgreSQL integration gate. It never replaces runtime data.

Provider-side encryption, versioning, private ACL, lifecycle, and independent credential policy require provider-side evidence. Client-side encryption is intentionally not implemented: without approved independent key management it would create unrecoverable-key risk. Encryption capability and remote durability are `NOT_VERIFIED`, not implied by a provider name. Retention remains `UNKNOWN` until size, RPO/RTO, region, and cost evidence exist. Evaluate daily/weekly/monthly lifecycle only after a successful restore drill; do not enable destructive expiration first.

## Failure handling

- Invalid OIDC token or unavailable required JWKS key: 401; never dev fallback.
- Valid identity without active membership: 403; never inferred tenant access.
- IdP/JWKS outage: liveness remains healthy; only valid cached keys within TTL verify.
- Interrupted upload: no final manifest, hence no advertised restore point.
- Missing object, bad checksum, corrupt archive, or restore failure: drill exits nonzero.
- Remote storage outage: backup fails; API liveness/readiness remains unchanged.

Use private systemd status/journals and runtime health. Public exposure still requires provider enrollment, membership workflow, remote bucket policy/encryption/lifecycle evidence, a successful real off-host restore, and separate TLS/reverse-proxy review.
