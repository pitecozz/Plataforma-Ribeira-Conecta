# Seven-day pilot readiness

**Assessed:** 2026-09-23
**Branch:** `feat/phase-1f-quality-masked-temporal-delta`
**Assessment rule:** readiness counts verified backend, customer workflow,
security, tests and deployment together. Documentation or a database table
alone does not raise a feature to `READY`.

## Current evidence-based readiness

| Measure | Current estimate | Basis |
|---|---:|---|
| `PILOT_READINESS_PERCENT` | 80% | The real Hamilton journey on the permanent origin has been manually verified through report and feedback UI. A server-side audit found that concurrent API transaction use left the feedback write uncommitted; the connection-level serialization fix is deployed pending one real feedback resubmission and audit check. |
| `FULL_PLATFORM_IMPLEMENTATION_PERCENT` | 23% | Shared backend foundations plus customer-facing Home/Farm360/report/feedback/decision workflow are implemented; most modules remain planned, foundation or research rather than customer workflows. |

These are deliberately conservative approximations, not service-level claims.

## P0 pilot path

| Capability | Backend | Frontend | Tests | State | Constraint / next gate |
|---|---|---|---|---|---|
| Login and tenant authorization | OIDC/RBAC/RLS contracts plus active audited VIEWER membership | exact runtime public-origin OIDC configuration | unit/integration + public OIDC PKCE smoke + prior real login | `PARTIAL` | The protected runtime uses the permanent origin, exact issuer, audience, JWKS, callback and CORS configuration outside Git. The public PKCE authorization handoff passes and no wildcard OIDC trust is permitted. A real Hamilton session must still be retested after the permanent-origin cutover. |
| Home and property portfolio | portfolio API | Home shell, honest cards and property selector | frontend unit | `PARTIAL` | No risk/asset count is shown without an API result. |
| Property boundary and Farm360 | property/boundary APIs | customer-readable map/workspace | unit + PostGIS + component regression | `PARTIAL` | A verified pilot operational-analysis boundary exists with explicit source, `MANUAL_CONFIRMED` classification and legal-boundary verification set to false. Migration 033 restores VIEWER `asset:read`; the UX separates known property data from unavailable optional context. Real-session retest is required after the V0.2 build. |
| Map | boundary and authenticated tiles | MapLibre property/asset layer and selection | frontend component + public smoke | `PARTIAL` | The map receives the persisted boundary and spatial assets, fits to the property geometry, and wires point selection to asset detail. It needs a real Hamilton browser retest; no fabricated contextual layers are shown. |
| Assets and Digital Twin | persisted asset inventory/API | customer-readable asset panel/detail and spatial layer | backend/frontend/PostGIS/RLS | `PARTIAL` | The verified initial pilot asset inventory is registered through the audited bootstrap. VIEWER has persisted `asset:read` only; write/manage permissions remain denied. The UI now hides property creation, boundary import and processing controls unless the authenticated permission profile authorizes them. |
| Context/evidence | scenes/products/provenance | provenance panel | backend/frontend | `PARTIAL` | Needs a simplified customer evidence view. |
| Risks/opportunities/actions | scoped decision/action outcome history API | Farm360 decision panel with honest empty state | unit/PostGIS/frontend | `PARTIAL` | It shows only persisted decisions/actions; commercial opportunities still require a separate evidence-backed workflow. |
| Intelligence Report V0.2 | loaded tenant records | printable HTML report | frontend unit | `PARTIAL` | It presents confirmed property/assets, unavailable context, decisions and limitations in customer language. Identifiers, checksums and machine values are confined to collapsed technical provenance and excluded from print. |
| Feedback | tenant-isolated feedback API and audit | Farm360 form with explicit submission/error state | backend/frontend/PostGIS | `PARTIAL` | The real UI submission returned 201, but its database transaction was left uncommitted by concurrent use of the shared API connection. Connection-level serialization is deployed; a real resubmission must prove the persisted feedback and matching audit event before this gate is `READY`. |
| Pilot E2E | public-access smoke plus real-session journey | `RIBEIRA_PLAYWRIGHT_BASE_URL` selects the protected permanent origin | official Playwright container | `PARTIAL` | HTTPS, public frontend/API health, unauthenticated 401, non-public metrics/docs/OpenAPI, and the Auth0 PKCE authorization handoff are proven against `https://app.ribeiraconecta.com.br`. A real Hamilton session has manually passed Home → Farm360 → map/assets → report; feedback must be resubmitted after the transaction-serialization deployment. |
| Secure external access | API, PostgreSQL and metrics loopback-only | production static ingress allowlists `/api/v1/*` and API health only | local + public ingress smoke | `READY` | The persistent named Cloudflare Tunnel provides HTTPS for `https://app.ribeiraconecta.com.br`; its protected runtime origin is not committed. Metrics, OpenAPI/docs and Redoc are non-public through the ingress policy; API/PostgreSQL/metrics listeners remain loopback-only. See [onboarding](pilot/PILOT_ONBOARDING.md). |

## Pilot delivery order

1. Integrate Home, Farm360, real asset/context/evidence surfaces.
2. Add report and feedback foundations with tenant isolation/audit.
3. Expose applicable decision/action information or honest empty states.
4. Preserve the active named Cloudflare Tunnel and exact protected
   OIDC/frontend/API configuration; changing the public origin requires a
   coordinated protected-configuration update and frontend rebuild.
5. Resubmit one real-user Farm360 feedback item after the API transaction
   serialization deployment, then verify its tenant/property association and
   matching audit record without reusing a development token.

## Verification environment

The isolated local PostGIS service is healthy on loopback. On the assessment
date the full integration suite executed from a freshly migrated isolated
database: **33 passed, 2 controlled external skips**. Controlled external provider tests
may remain skipped; pilot-critical database tests may not be silently skipped.

## Explicit non-goals for the pilot week

No fake customer data, unapproved satellite flood claim, automated irrigation,
radio-coverage assertion, Earth Engine integration, laboratory result
fabrication, CRNS implementation or public database/metrics exposure.
