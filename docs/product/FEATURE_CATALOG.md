# Feature catalogue

This is the canonical feature index. Lifecycle states are `IDEA`, `PLANNED`,
`FOUNDATION`, `PARTIAL`, `BETA`, `PRODUCTION`, `DEFERRED`, `BLOCKED`, and
`RESEARCH`. `IMPLEMENTED` below means a tested repository capability, not a
claim that every customer workflow is production-operated. All features require
tenant isolation, auditability, provenance and explicit limitations.

| FEATURE_ID | Feature / module | Status | Purpose and user value | Main dependencies and data | Evidence/security/availability |
|---|---|---|---|---|---|
| F-CORE-001 | Tenant Digital Twin / Maps / Farm360 | `FOUNDATION` | Operator and customer representation of property and physical assets. | Property/asset geometry, ownership, source, timestamps; PostGIS/RLS. | Manual facts stay `MANUAL_CONFIRMED`; no inferred equipment. Property asset inventory is `asset:read`-gated; broader rule asset scope remains pending. |
| F-RULE-001 | Scoped Rules, decisions, actions and outcomes | `PARTIAL` | Makes context yield a traceable, non-automated recommendation and closure. | Versioned rule, evidence, property scope, action/result. | Tenant/property scope only; broader inheritance pending. `engine.py`, `service.py`, migration 029/031. |
| F-FLOOD-001 | Flood event and exposure | `FOUNDATION` | Reusable evidence-backed event, hypothesis and tenant exposure context. | Official event facts, verified zones, property/asset geometry. | H1–H4 remain independent; no causal claim/no seeded real extent. `flood_pilot.py`, migration 030, `test_flood_sar.py`. |
| F-RS-001 | Sentinel scene catalogue and provenance | `PARTIAL` | Select reproducible satellite scenes for spatial analysis. | Official CDSE STAC item metadata and exact footprints. | No Process API scene proof; provider contract is bounded. `sentinel1_discovery.py`, `test_sentinel1_discovery.py`. |
| F-RS-002 | Registro Sentinel-1 V2 pair | `FOUNDATION` | Validated flood-analysis input for a later authorized processor. | 2026-09-06/12 exact catalogue footprints, common Registro coverage. | No flood classification or new Process API request; see [scene selection](../geospatial/SCENE_SELECTION.md). |
| F-PROSPECT-001 | Prospect/environment profile | `PLANNED` | Explainable qualification and opportunity review. | Permitted public and manually confirmed context. | No contact or need fabrication; LGPD/minimization gate. |
| F-CONNECT-001 | Connectivity feasibility | `PLANNED` | Reviewable connectivity assessment. | Confirmed POP/tower/DEM/field facts. | No inferred availability; engineering review required. |
| F-IOT-001 | Telemetry ingress | `PLANNED` | Safe sensor observations feeding rules. | Tenant-bound device, unit, calibration, quality/time, provider. | Authenticated MQTT/HTTPS only; no fabricated telemetry. [Telemetry](../iot/FIELD_TELEMETRY.md). |
| F-SOIL-001 | Soil Intelligence | `PLANNED` | Evidence-separated soil/environment context for Farm360/Agro. | Terrain, remote context, weather, field and lab data. | Satellite/model != lab/in-situ. [Soil](../agro/SOIL_INTELLIGENCE.md). |
| F-AGRO-001 | Agricultural land suitability | `PLANNED` | Explainable preliminary/validated planting assessment. | Verified property/field, analysis area, approved crop policy, later lab/field evidence. | Drawn area is not legal boundary; no unexplained score. [Suitability](../agro/AGRICULTURAL_SUITABILITY.md). |
| F-AGRO-002 | Banana Suitability Intelligence | `PLANNED` | Crop-specific suitability and validation workflow. | F-AGRO-001 plus approved agronomic sources. | Disease/management policy is `EXPERT_VALIDATION_REQUIRED`. |
| F-AGRO-003 | Management zones and smart sampling | `PLANNED` | Target field/lab effort using evidence-derived zones. | Terrain, historic variation, samples and sensors as available. | Suggested location is `DERIVED_LOCATION`, not lab evidence. [Sampling](../agro/SMART_SOIL_SAMPLING.md). |
| F-AGRO-004 | Virtual soil sensor/water balance/irrigation support | `RESEARCH` | Contextual moisture and water-risk support. | Calibrated sensors, weather, soil/terrain and validated models. | Estimate is `DERIVED`/`PREDICTED`; no autonomous irrigation. |
| F-AGRO-005 | Drone, mobile EC and plant response | `RESEARCH` | Localized validation and variability context. | Flight/device metadata or contextual survey evidence. | EC is indirect; imagery does not diagnose disease. |
| F-BUS-001 | Commercial catalogue, contracts and pricing simulation | `PARTIAL` | Governed commercial operations and incomplete-pricing handling. | Versioned policy, ownership, capacity, evidence. | Does not establish final market price. `business*.py`, `test_business.py`, migration 006. |
| F-TRACE-001 | Traceability | `FOUNDATION` | Audit/evidence chain across operational decisions. | Audit log, source/evidence/rule/version links. | Harvest/packing/transport trace remains later. |
| F-AI-001 | Contextual AI | `DEFERRED` | Permissioned assistance over grounded context. | Governed corpus, authorization, evaluation. | No ungrounded advice or autonomous decision. |

## Required feature record

Every new `FEATURE_ID` must state: name, module, lifecycle, purpose, persona,
business value, dependencies, data/providers, business-rule and security
requirements, Evidence First requirement, limitations, API/UI surface, tests,
documentation links and commercial availability. A detailed feature document
may hold the full record; this index must link to it.

## Implementation evidence audit

This initial audit links existing repository capabilities without duplicating
their API schemas or migrations. It is expanded as future features ship.

| Capability | Code / API surface | Persistence | Tests / detailed documentation |
|---|---|---|---|
| Digital Twin spatial assets | `business_service.py`, `business_repository.py`, property-assets route in `api.py` | migration 028 | `test_business.py`, `test_farm360_api.py`, [Farm360](../geospatial/FARM_360_V1.md) |
| Scoped rule/action/outcome | `service.py`, rule payload and outcome route in `api.py` | migrations 029 and 031 | `test_vertical_slice.py`, [rule catalogue](../rules/BUSINESS_RULE_CATALOG.md) |
| Flood exposure foundation | `flood_pilot.py`, `POST /v1/tenants/{tenant_id}/flood-exposure-assessments` | migration 030 | `test_flood_sar.py`, [delivery plan](../CODEX_AUTONOMOUS_DELIVERY.md) |
| Satellite catalogue | `geospatial_service.py`, satellite search routes in `api.py` | geospatial scene/asset migrations | `test_sentinel1_discovery.py`, [provider](../geospatial/COPERNICUS_PROVIDER.md) |
| Commercial engine | `business.py`, `business_service.py`, commercial routes in `api.py` | migration 006 | `test_business.py`, [business rules](../business/RIBEIRA_BUSINESS_RULES.md) |

## Documentation debt register

| Priority | Capability | Missing material | Owner/status |
|---|---|---|---|
| High | Digital Twin | Customer workflow and Farm360 UI guide once stable. | `PLANNED` with F-CORE-001 follow-on. |
| High | Rule/outcome | Canonical end-user rule/action/outcome operation guide. | Next rule increment. |
| High | Flood foundation | Operator flood-event/exposure runbook once real provider ingestion is authorized. | Blocked on verified input/operating process. |
| Medium | Existing API | Consolidated endpoint reference generated from OpenAPI. | `PLANNED`; avoid duplicating API schema now. |
| Medium | Commercial engine | Service-facing explanation of existing pricing simulation boundaries. | Linked from F-BUS-001; expand after policy validation. |
