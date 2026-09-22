# Seven-day pilot readiness

**Assessed:** 2026-09-22
**Branch:** `feat/phase-1f-quality-masked-temporal-delta`
**Assessment rule:** readiness counts verified backend, customer workflow,
security, tests and deployment together. Documentation or a database table
alone does not raise a feature to `READY`.

## Current evidence-based readiness

| Measure | Current estimate | Basis |
|---|---:|---|
| `PILOT_READINESS_PERCENT` | 50% | Tenant/RLS, Home, property/boundary, Farm360 map/provenance/assets, Report V0.1, audited feedback and persisted decision/action history work; pilot E2E and HTTPS path do not. |
| `FULL_PLATFORM_IMPLEMENTATION_PERCENT` | 23% | Shared backend foundations plus customer-facing Home/Farm360/report/feedback/decision workflow are implemented; most modules remain planned, foundation or research rather than customer workflows. |

These are deliberately conservative approximations, not service-level claims.

## P0 pilot path

| Capability | Backend | Frontend | Tests | State | Constraint / next gate |
|---|---|---|---|---|---|
| Login and tenant authorization | OIDC/RBAC/RLS contracts | exact runtime public-origin OIDC configuration | unit/integration | `BLOCKED` | A verified pilot tenant, operational-analysis property boundary and manually confirmed initial assets now exist through the private audited bootstrap. The protected runtime remains in development-auth mode and has no active pilot OIDC membership; the operator must supply verified issuer and subject before production OIDC/membership configuration. No wildcard OIDC trust is permitted. |
| Home and property portfolio | portfolio API | Home shell, honest cards and property selector | frontend unit | `PARTIAL` | No risk/asset count is shown without an API result. |
| Property boundary and Farm360 | property/boundary APIs | map/workspace | unit + PostGIS | `PARTIAL` | A verified pilot operational-analysis boundary exists with explicit source, `MANUAL_CONFIRMED` classification and legal-boundary verification set to false. The authenticated customer workflow is still pending OIDC and production ingress configuration. |
| Map | boundary and authenticated tiles | MapLibre property/NDVI/delta layers | frontend/E2E validation | `PARTIAL` | Asset layer/click detail is being added; no fabricated contextual layers. |
| Assets and Digital Twin | persisted asset inventory/API | asset panel/detail and spatial layer | backend/frontend/PostGIS | `PARTIAL` | The verified initial pilot asset inventory is registered through the audited bootstrap; authenticated customer visibility remains pending OIDC and production ingress configuration. |
| Context/evidence | scenes/products/provenance | provenance panel | backend/frontend | `PARTIAL` | Needs a simplified customer evidence view. |
| Risks/opportunities/actions | scoped decision/action outcome history API | Farm360 decision panel with honest empty state | unit/PostGIS/frontend | `PARTIAL` | It shows only persisted decisions/actions; commercial opportunities still require a separate evidence-backed workflow. |
| Intelligence Report V0.1 | loaded tenant records | printable HTML report | frontend unit | `PARTIAL` | It exposes available property/assets/provenance and explicit unknown decisions; report API/history is later. |
| Feedback | tenant-isolated feedback API and audit | Farm360 form with explicit submission/error state | backend/frontend/PostGIS | `PARTIAL` | Creates no operational conclusion; triage/listing workflow is later. |
| Pilot E2E | legacy private validation spec | `RIBEIRA_PLAYWRIGHT_BASE_URL` can select the exact Quick Tunnel origin | container browser exercised | `BLOCKED` | Current spec asserts a superseded validation workspace; real OIDC E2E requires the live Quick Tunnel origin, Auth0 registration and an operator-provisioned pilot identity. It must not reuse development-token data. |
| Secure external access | API, PostgreSQL and metrics loopback-only | production static ingress proxies only `/api` to loopback API | local ingress/proxy test | `PARTIAL` | `CLOUDFLARE_QUICK_TUNNEL=PILOT_TEST_ONLY`. The live static process predates the `/api` proxy deployment, so public `/api/health/*` currently returns `404`. Do not restart it against a development-auth API. First complete protected production OIDC configuration and verified tenant onboarding, then rebuild/restart the API and static ingress together. `https://app.ribeiraconecta.com.br` is deferred as `FUTURE_CUSTOM_DOMAIN`. See [onboarding](pilot/PILOT_ONBOARDING.md). |

## Pilot delivery order

1. Integrate Home, Farm360, real asset/context/evidence surfaces.
2. Add report and feedback foundations with tenant isolation/audit.
3. Expose applicable decision/action information or honest empty states.
4. Start the Quick Tunnel, then register its exact temporary origin with Auth0
   and the protected frontend/API configuration.
5. Provision the pilot membership, then run final-host OIDC E2E without
   reusing development-token data.

## Verification environment

The isolated local PostGIS service is healthy on loopback. On the assessment
date the full integration suite executed with configured test database URLs:
**33 passed, 2 controlled external skips**. Controlled external provider tests
may remain skipped; pilot-critical database tests may not be silently skipped.

## Explicit non-goals for the pilot week

No fake customer data, unapproved satellite flood claim, automated irrigation,
radio-coverage assertion, Earth Engine integration, laboratory result
fabrication, CRNS implementation or public database/metrics exposure.
