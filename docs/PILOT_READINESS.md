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
| Login and tenant authorization | OIDC/RBAC/RLS contracts | OIDC session configuration | unit/integration | `PARTIAL` | Pilot identity-provider configuration and user membership are not yet performed. |
| Home and property portfolio | portfolio API | Home shell, honest cards and property selector | frontend unit | `PARTIAL` | No risk/asset count is shown without an API result. |
| Property boundary and Farm360 | property/boundary APIs | map/workspace | unit + PostGIS | `PARTIAL` | Core flow exists; the customer workflow is not yet consolidated. |
| Map | boundary and authenticated tiles | MapLibre property/NDVI/delta layers | frontend/E2E validation | `PARTIAL` | Asset layer/click detail is being added; no fabricated contextual layers. |
| Assets and Digital Twin | persisted asset inventory/API | asset panel/detail and spatial layer | backend/frontend/PostGIS | `PARTIAL` | Asset registration and pilot asset onboarding remain operational steps. |
| Context/evidence | scenes/products/provenance | provenance panel | backend/frontend | `PARTIAL` | Needs a simplified customer evidence view. |
| Risks/opportunities/actions | scoped decision/action outcome history API | Farm360 decision panel with honest empty state | unit/PostGIS/frontend | `PARTIAL` | It shows only persisted decisions/actions; commercial opportunities still require a separate evidence-backed workflow. |
| Intelligence Report V0.1 | loaded tenant records | printable HTML report | frontend unit | `PARTIAL` | It exposes available property/assets/provenance and explicit unknown decisions; report API/history is later. |
| Feedback | tenant-isolated feedback API and audit | Farm360 form with explicit submission/error state | backend/frontend/PostGIS | `PARTIAL` | Creates no operational conclusion; triage/listing workflow is later. |
| Pilot E2E | validation E2E only | validation workspace only | Playwright | `MISSING` | Requires isolated pilot fixture and full customer path. |
| Secure external access | loopback services/health endpoints | static build | local checks | `BLOCKED` | `PILOT_ACCESS_DECISION_REQUIRED`; Cloudflare remains `DEFERRED_BY_OPERATOR`. |

## Pilot delivery order

1. Integrate Home, Farm360, real asset/context/evidence surfaces.
2. Add report and feedback foundations with tenant isolation/audit.
3. Expose applicable decision/action information or honest empty states.
4. Create safe non-customer E2E fixtures for the complete path.
5. Complete identity provisioning, deployment runbook and operator-approved HTTPS
   access without exposing PostgreSQL, metrics or development services.

## Verification environment

The isolated local PostGIS service is healthy on loopback. On the assessment
date the full integration suite executed with configured test database URLs:
**33 passed, 2 controlled external skips**. Controlled external provider tests
may remain skipped; pilot-critical database tests may not be silently skipped.

## Explicit non-goals for the pilot week

No fake customer data, unapproved satellite flood claim, automated irrigation,
radio-coverage assertion, Earth Engine integration, laboratory result
fabrication, CRNS implementation or public database/metrics exposure.
