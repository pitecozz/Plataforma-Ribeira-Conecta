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
| Pilot feedback | `POST /v1/tenants/{tenant_id}/pilot-feedback`, Farm360 feedback panel | migration 032 | `test_api.py`, `test_postgres_integration.py`, `PilotFeedbackPanel.test.tsx`, [pilot quick start](../training/PILOT_QUICK_START.md) |
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

## Full platform coverage audit — pilot fast track

The following rows complete the architecture-level audit of currently defined
capabilities. A row marked `COMING_SOON`, `RESEARCH`, `BLOCKED` or `DEFERRED`
is not an operational customer feature and must be hidden or clearly labelled
in navigation. Dependencies, data needs, Evidence First/security boundaries and
commercial availability are summarized here and expanded in the linked canon.

| FEATURE_ID | Module / name | State | Dependencies and data | Evidence/security/business boundary | Commercial availability / docs |
|---|---|---|---|---|---|
| F-MAPS-002 | Maps / layers, click inspection and spatial context | `PARTIAL` | Verified boundary/assets/layers with source/date. | Layer is not evidence alone; tenant map reads stay authorized. | Pilot map; [Farm360](../geospatial/FARM_360_V1.md). |
| F-MAPS-003 | Geometry versioning, GeoJSON import and approval | `BETA` | Property, import bytes, CRS, reviewer/audit. | Drawn/imported geometry is not legal title; approval is segregated. | Onboarding service; [boundary workflow](../geospatial/FARM_360_V1.md). |
| F-FARM-002 | Farm360 integrated property workspace | `PARTIAL` | F-CORE-001 plus context/evidence/actions. | Displays classification, source/date and missing data. | Pilot P0; [readiness](../PILOT_READINESS.md). |
| F-ASSET-002 | Asset context, click/detail and infrastructure inventory | `PARTIAL` | Persisted Digital Twin assets/geometry/source/context. | No inferred equipment/condition; `asset:read` and RLS. | Pilot P0; [Farm360](../geospatial/FARM_360_V1.md). |
| F-PROSPECT-002 | Prospect registration, conversion and qualification | `COMING_SOON` | Permitted prospect/customer/property context and service catalogue. | Evidence -> need -> service -> opportunity; LGPD minimization. | Future commercial workflow. |
| F-CONNECT-002 | Connectivity context and network-asset planning | `COMING_SOON` | Confirmed POP/tower/road/asset/terrain data. | No radio coverage or availability claim without model/input/assumptions. | Assessment project. |
| F-ENERGY-001 | Energy assets, telemetry and opportunity context | `COMING_SOON` | Confirmed energy inventory/measurements/outage sources. | No fabricated consumption/power quality. | Assessment/monitoring later. |
| F-AGRO-006 | Agro field/crop/inspection and vegetation context | `COMING_SOON` | Verified field/crop, remote/weather/inspection evidence. | Remote signal is triage, not crop diagnosis. | Consulting/monitoring later. |
| F-BANANA-002 | Banana field intelligence and inspection workflow | `COMING_SOON` | F-AGRO-006 and approved agronomic source. | Disease rules are `EXPERT_VALIDATION_REQUIRED`. | Expert-backed service only. |
| F-SOIL-002 | Soil baseline, remote context and field evidence | `COMING_SOON` | Provider-neutral soil/terrain/weather, sensors/labs. | Remote estimate != field observation != lab measurement. | [Soil](../agro/SOIL_INTELLIGENCE.md). |
| F-AGRO-007 | Can I Plant Here / preliminary suitability | `COMING_SOON` | Verified property/field/analysis area/crop policy. | Analysis area is not legal demarcation; no unexplained score. | [Suitability](../agro/AGRICULTURAL_SUITABILITY.md). |
| F-AGRO-008 | Banana suitability | `COMING_SOON` | Suitability + approved banana factors/expert policy. | Never promotes preliminary to validated. | Expert-backed later. |
| F-AGRO-009 | Georeferenced laboratory integration | `COMING_SOON` | Sample chain, lab/method/unit/raw result. | Lab result applies only to its sample/time/depth. | Lab integration service. |
| F-IOT-002 | Field telemetry/device health | `COMING_SOON` | Tenant device/asset, MQTT/HTTPS adapter, calibration/units/time. | Authenticated/replay-safe only; no synthetic live data. | [Telemetry](../iot/FIELD_TELEMETRY.md). |
| F-DRONE-001 | Drone survey | `RESEARCH` | Flight, payload, capture/spatial accuracy/source metadata. | Complements satellite/field evidence; no silent substitution. | Optional field service. |
| F-AGRO-010 | CRNS soil moisture | `RESEARCH` | Specialized instrument/business or research case. | Area-integrated measurement still needs calibration/provenance. | No pilot offer. |
| F-FLOOD-002 | Rain, river, discharge, reservoir and source health | `FOUNDATION` | Official/provider-specific time series/event provenance. | H1-H4 stay independent; missing input stays unknown. | [Flood plan](../CODEX_AUTONOMOUS_DELIVERY.md). |
| F-FLOOD-003 | Municipal/property/asset/agricultural exposure | `FOUNDATION` | Verified hazard geometry plus tenant geometry. | No extent/exposure calculation from unverified/satellite-only signal. | Environmental assessment later. |
| F-RS-003 | Provider-neutral missions/datasets | `FOUNDATION` | CDSE, future GEE/USGS/NASA/JRC; Sentinel/Landsat/DEM/SMAP. | Explicit provider selection/compatibility; Google Earth visualization excluded. | [Provider policy](../geospatial/PROVIDER_ABSTRACTION.md). |
| F-RS-004 | Sentinel-1 flood analysis | `FOUNDATION` | Registro V2 pair/V3 tile and authorized processor. | Catalogue selection is not flood classification. | Deferred environmental input. |
| F-MON-001 | Monitor/source freshness/events/time series | `COMING_SOON` | Provider/telemetry observations, quality and rules. | Provider health/failure stays explicit. | Monitoring subscription later. |
| F-RULE-002 | Rule applicability: customer, field, zone, asset and crop | `COMING_SOON` | Shared Digital Twin scope hierarchy/versioning. | Do not silently inherit global rules. | Rules P1 follow-on. |
| F-TRACE-002 | Customer evidence/action/outcome view | `BETA` | Tenant property decision/action history and linked evidence identifiers. | Shows only persisted outcomes and explicit empty state; no inferred commercial opportunity. | Farm360 pilot panel. |
| F-AI-002 | Contextual assistance and report explanation | `DEFERRED` | Permissioned corpus, evaluated prompts and citations. | Cannot override evidence/rules/security. | Not pilot. |
| F-BUS-002 | Evidence-backed cross-sell/upsell | `PARTIAL` | Commercial evidence, need and applicable service. | No arbitrary sales recommendation. | Internal/commercial workflow. |
| F-REPORT-001 | Intelligence Report framework | `BETA` | Tenant property/assets/context/evidence/decisions. | HTML V0.1 shows loaded records and explicit unavailable decisions; no report history/API yet. | Pilot Report V0.1. |
| F-FEEDBACK-001 | Pilot feedback | `BETA` | Authenticated tenant/user/page/property/feature/type/message/audit. | Feedback is a product input, not environmental/commercial evidence; RLS and same-tenant property validation apply. | Farm360 pilot form; triage/listing is later. |
| F-UX-001 | Product navigation and feature-state flags | `BETA` | Canonical feature lifecycle and authorization. | Home/Farm360/Help are interactive; other modules are visible status labels, never dead buttons. | Pilot shell. |
| F-SEC-002 | Pilot identity/onboarding/deployment path | `PARTIAL` | OIDC membership, HTTPS edge/operator decision, runbooks. | No public DB/metrics/dev ports; Cloudflare decision preserved. | `BLOCKED` pending operator access decision. |
