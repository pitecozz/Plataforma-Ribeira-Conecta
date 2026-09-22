# Seven-day pilot readiness

**Assessed:** 2026-09-22
**Branch:** `feat/phase-1f-quality-masked-temporal-delta`
**Assessment rule:** readiness counts verified backend, customer workflow,
security, tests and deployment together. Documentation or a database table
alone does not raise a feature to `READY`.

## Current evidence-based readiness

| Measure | Current estimate | Basis |
|---|---:|---|
| `PILOT_READINESS_PERCENT` | 75% | Tenant/RLS, pilot property/assets, audited VIEWER membership, production OIDC build and temporary HTTPS ingress are operational. Public pre-authentication E2E passes; a real customer-session journey remains unverified. |
| `FULL_PLATFORM_IMPLEMENTATION_PERCENT` | 23% | Shared backend foundations plus customer-facing Home/Farm360/report/feedback/decision workflow are implemented; most modules remain planned, foundation or research rather than customer workflows. |

These are deliberately conservative approximations, not service-level claims.

## P0 pilot path

| Capability | Backend | Frontend | Tests | State | Constraint / next gate |
|---|---|---|---|---|---|
| Login and tenant authorization | OIDC/RBAC/RLS contracts plus active audited VIEWER membership | exact runtime public-origin OIDC configuration | unit/integration + public OIDC-gate smoke | `PARTIAL` | The protected runtime is production/OIDC mode and uses exact issuer, audience, JWKS, callback and CORS configuration outside Git. The public flow reaches Auth0 with PKCE; completion with the real user session is still required. No wildcard OIDC trust is permitted. |
| Home and property portfolio | portfolio API | Home shell, honest cards and property selector | frontend unit | `PARTIAL` | No risk/asset count is shown without an API result. |
| Property boundary and Farm360 | property/boundary APIs | map/workspace | unit + PostGIS | `PARTIAL` | A verified pilot operational-analysis boundary exists with explicit source, `MANUAL_CONFIRMED` classification and legal-boundary verification set to false. Customer-session UI verification remains pending. |
| Map | boundary and authenticated tiles | MapLibre property/NDVI/delta layers | frontend/E2E validation | `PARTIAL` | Asset layer/click detail is being added; no fabricated contextual layers. |
| Assets and Digital Twin | persisted asset inventory/API | asset panel/detail and spatial layer | backend/frontend/PostGIS | `PARTIAL` | The verified initial pilot asset inventory is registered through the audited bootstrap; authenticated customer visibility remains pending customer-session E2E. |
| Context/evidence | scenes/products/provenance | provenance panel | backend/frontend | `PARTIAL` | Needs a simplified customer evidence view. |
| Risks/opportunities/actions | scoped decision/action outcome history API | Farm360 decision panel with honest empty state | unit/PostGIS/frontend | `PARTIAL` | It shows only persisted decisions/actions; commercial opportunities still require a separate evidence-backed workflow. |
| Intelligence Report V0.1 | loaded tenant records | printable HTML report | frontend unit | `PARTIAL` | It exposes available property/assets/provenance and explicit unknown decisions; report API/history is later. |
| Feedback | tenant-isolated feedback API and audit | Farm360 form with explicit submission/error state | backend/frontend/PostGIS | `PARTIAL` | Creates no operational conclusion; triage/listing workflow is later. |
| Pilot E2E | legacy private validation spec plus configurable public-access smoke | `RIBEIRA_PLAYWRIGHT_BASE_URL` selects the exact Quick Tunnel origin | official Playwright container: public smoke passes | `PARTIAL` | HTTPS, public frontend/API health, unauthenticated 401, OIDC PKCE/root callback and non-public metrics are proven. The complete Home → Farm360 → report → feedback journey still requires a real operator-controlled Auth0 session and must not reuse development-token data. |
| Secure external access | API, PostgreSQL and metrics loopback-only | production static ingress allowlists `/api/v1/*` and API health only | local + public ingress smoke | `READY` | `CLOUDFLARE_QUICK_TUNNEL=PILOT_TEST_ONLY`; exact origin is protected runtime state. Public frontend and API health respond over HTTPS; metrics, OpenAPI/docs and Redoc return 404, while API/PostgreSQL/metrics listeners remain loopback-only. `https://app.ribeiraconecta.com.br` is deferred as `FUTURE_CUSTOM_DOMAIN`. See [onboarding](pilot/PILOT_ONBOARDING.md). |

## Pilot delivery order

1. Integrate Home, Farm360, real asset/context/evidence surfaces.
2. Add report and feedback foundations with tenant isolation/audit.
3. Expose applicable decision/action information or honest empty states.
4. Preserve the active Quick Tunnel and exact protected OIDC/frontend/API
   configuration; changing the temporary origin requires coordinated rebuild.
5. Complete the real-user Auth0 session and run the authenticated customer
   journey plus cross-tenant denial without reusing development-token data.

## Verification environment

The isolated local PostGIS service is healthy on loopback. On the assessment
date the full integration suite executed with configured test database URLs:
**33 passed, 2 controlled external skips**. Controlled external provider tests
may remain skipped; pilot-critical database tests may not be silently skipped.

## Explicit non-goals for the pilot week

No fake customer data, unapproved satellite flood claim, automated irrigation,
radio-coverage assertion, Earth Engine integration, laboratory result
fabrication, CRNS implementation or public database/metrics exposure.
