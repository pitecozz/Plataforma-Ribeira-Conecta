# Autonomous delivery plan — requirements resync

**Updated:** 2026-09-23
**Authority order:** explicit current Product Owner requirements, documented
Ribeira business rules, product blueprint, customer configuration, official
provider contracts, collected data, deterministic calculation, model, then
assumption.

## Product direction

Ribeira Conecta is an operational decision platform, not a collection of
dashboards. Each module must contribute to:

```text
asset -> data -> context -> rule -> decision -> action -> result
```

The platform must support prospect discovery, a real understanding of the
customer environment, installations and physical assets, connectivity, energy,
environmental/operational risks, banana-producer consulting, monitoring,
alerts, recommendations, automation, and responsible cross-sell/upsell. Scope
must be configurable by sector, customer, property, field/talhão, and asset.

Evidence First is non-negotiable: unknown input remains unknown; a model or
satellite product never becomes an observation or diagnosis; decisions preserve
source, time, transformations, rule/model version, limitations, conflicts, and
outcomes.

## Cross-cutting documentation, training and commercial discipline

Documentation is a product completion requirement, not a release afterthought.
`docs/README.md` is the canonical role-based portal; its feature, module,
service, source/data, integration and rule catalogues are the only indexes of
their kind. Every major increment updates those references or records bounded
documentation debt. Ribeira Academy is planned documentation/training content,
not a separate product at this stage.

## Production promotion policy

Source delivery is deliberately independent from public release promotion.
Coherent increments are committed and pushed after their relevant verification,
but the running customer release is not rebuilt or restarted for every source
commit. A frontend candidate must be built outside `frontend/dist` from the
protected production/OIDC configuration, pass configuration preflight,
relevant tests, a production build and an isolated candidate smoke check before
an operator promotes it. Promotion retains the previous static artifact and
automatically restores it if local or public health checks fail. A failed
candidate is recorded as delivery evidence and never knowingly replaces the
known-good public release. See
[`PRODUCTION_RUNTIME_FOUNDATION.md`](operations/PRODUCTION_RUNTIME_FOUNDATION.md#frontend-release-candidates).

Commercial packaging follows an Evidence-First **hybrid** hypothesis:
onboarding/initial study + recurring platform subscription + optional
consulting, field services, hardware and third-party costs. It is not a final
price list. Prices, margins and unit economics remain `TO_VALIDATE` until real
cost, capacity and customer evidence exist; this cross-cutting work does not
reorder the current shared-foundation priorities.

## Full-platform acceleration record

The Hamilton pilot has proven OIDC, RLS, audited persistence and the named
Cloudflare ingress. The former pilot-only delivery constraint is superseded:
full-platform development is enabled, but each module must deliver an actual
tenant-safe workflow rather than a shell or status badge. The immediate
execution order is property-first Farm360 and Maps, Digital Twin assets, data
availability/context, reports, remote sensing, environmental/flood, Agro,
Soil, telemetry, Connect, Energy, Prospect/Business and contextual AI.
Dependencies, evidence gates and provider/operator constraints below remain in
force. The real Hamilton property is a continuous acceptance dataset; its
facts and missing data are never changed merely to make a workflow pass.

## Requirements resync and supersession record

The blueprint's historical Phase 1 lists broad data integrations and satellite
work. Recent delivery concentrated on Vale/Ribeira hydrology and a Registro SAR
pilot, which is valid enabling work but cannot define the whole roadmap.

The current explicit priority supersedes an **imagery-first sequencing
interpretation**, not the historical work itself. The Registro Sentinel-1 V2
catalogue selection remains preserved and valid, but is now an environmental
risk input awaiting a separately authorized processing increment. Shared asset,
context, scoped rules, and operational outcomes take priority over more SAR
processing or unrelated municipal tiles.

## Remote-sensing provider strategy

CDSE, optional Google Earth Engine, USGS/NASA, JRC and future services are
independent providers behind common catalogue, asset-access and processing
interfaces. Sentinel-1/Sentinel-2 and Landsat 8/9 remain mission/dataset
identities rather than provider lock-in. Every output preserves provider,
dataset/collection, item/asset, request, processing and compatibility
provenance. Provider redundancy is explicit and policy-driven; it never masks a
failure, mixes unlike products, or falls back to Google Earth visualization
imagery. Earth Engine integration is `LATER`; see
`docs/geospatial/PROVIDER_ABSTRACTION.md`.

## Primary real-world validation case: Vale do Ribeira flood, September 2026

`VALE_RIBEIRA_FLOOD_2026_09_FACTUAL_EVIDENCE_ONLY` is a primary reusable
validation case for flood intelligence, not a Sentinel-1 experiment. The
persisted operational event is retained as factual evidence only; it must be
able to connect municipality/property/asset exposure, rainfall, river and
reservoir context, satellite evidence, rules, recommended actions and later
results through the core chain.

Known inputs are maintained independently: September rainfall and accumulation
windows; municipal flood evidence (including Registro and, where persisted and
verified, Eldorado, Sete Barras and Iguape); official IBGE municipal geometries;
Copel timing; river conditions where official evidence exists; Sentinel-1/S2
investigation; and municipal banana/agricultural context. A missing river level,
property exposure, asset exposure, upstream measurement or satellite-derived
extent remains explicitly unknown.

No causal conclusion is encoded. The required hypotheses are separate records
with the only permitted states `SUPPORTED`, `PARTIALLY_SUPPORTED`,
`INCONCLUSIVE`, `CONTRADICTED`, and `UNKNOWN`:

| Hypothesis | Current treatment |
|---|---|
| H1 — local rainfall contribution | `INCONCLUSIVE`; evaluate against time/location-specific rainfall and exposure evidence. |
| H2 — upstream rainfall contribution | `UNKNOWN` until verified upstream rainfall/river sequence is available. |
| H3 — reservoir/Capivari operation contribution | `INCONCLUSIVE`; preserve Copel timing without asserting contribution. |
| H4 — ENSO/El Niño broader climate context | `INCONCLUSIVE`; context only, never `EL_NINO_CAUSED_FLOOD=true`. |

Flood capability must answer what/where/when, municipality/property/asset
exposure, rainfall accumulation, river trajectory, upstream sequence, reservoir
timing, satellite evidence, unknowns, at-risk customers/prospects and the
evidence for each recommended action. It is reusable for future events and must
not hard-code a one-off municipal conclusion.

## Architecture coverage review

| Module | Current state | Main gap/dependency | Priority |
|---|---|---|---|
| Maps / Farm360 | Property GIS, scene catalogue, derived-product map, provenance | unified physical-asset/digital-twin layers | NOW |
| Business / Prospect | Customer, contract, opportunity evidence, score foundation | public-data prospect intake and environment profile | NOW/NEXT |
| Rules / Monitor | Versioned rule and alert/action chain | sector/customer/property/field/asset inheritance and feedback | NOW |
| Connect | Asset/contract primitives | POP/tower inventory, LoS/Fresnel, feasibility evidence | NEXT |
| Agro / Banana | Rainfall, municipal baseline and imagery foundations | fields, verified agronomic observations, inspection workflow | NEXT |
| IoT | Architecture only | device, telemetry, MQTT/LoRaWAN, replay-safe pipeline | NEXT |
| Energy / Security | Commercial asset primitives | spatial inventory, condition data and operational rules | NEXT |
| Trace | Audit/evidence implemented | batch/harvest/packing/transport chain | LATER |
| AI | Deliberately absent | governed contextual corpus, permissions and evaluation | LATER |
| Environmental risk | Rainfall timeline and validated Registro S1 pair | authorized processing and customer/property linkage | DEFERRED |
| Soil Intelligence / Agro | Municipal baseline, terrain/remote-provider architecture and flood context | fields, analysis areas, lab/sample chain, management zones and approved agronomic policy | NEXT |

## NOW

### 1. Digital Twin asset and context foundation

- **Status:** persistence/API, tenant-scoped inventory/map rendering and an
  `asset:manage`-gated Farm360 registration form are implemented. The form
  requires factual source and observation time, and never derives a location
  when coordinates are absent. When its persisted boundary is available, an
  operator may select an optional provisional point on the same tenant-scoped
  map; it only populates the form and is never stored without the sourced
  confirmation. Each registration now also produces tenant-local `ASSET_REGISTRATION` evidence with its submitted source reference, observation timestamp, classification and explicit limitations; this does not make an asset a measurement or an asset-scoped rule. Asset-specific scoped-rule consumption and inheritance remain follow-on work.
- **Objective:** add tenant-isolated, spatial physical assets and context links
  for installations, connectivity, energy, security, agricultural and
  operational assets.
- **Business value:** gives Farm360, Prospect, Connect, Energy, Security, IoT
  and Agro one factual customer-environment representation.
- **Required data:** manually confirmed asset type, geometry/CRS, ownership,
  operational status, source and timestamps; absent attributes remain unknown.
- **Dependencies:** existing customer/property/asset ownership and PostGIS/RLS.
- **Evidence First gate:** no inferred equipment, network, energy availability
  or agronomic state; classify manual field records explicitly.
- **Security gate:** tenant RLS/FKs, role-gated writes, audit every mutation;
  document references must be opaque and allowlisted.
- **Tests:** geometry/CRS, tenant isolation, ownership temporal integrity,
  audit, unknown values and API authorization.
- **Completion criteria:** an asset links to a property, appears in Farm360,
  supplies evidence to a scoped rule, and retains an action/result trail.

### 2. Scoped rule-to-outcome extension

- **Status:** the first property-evaluation-to-human-result slice is implemented:
  The customer/field inheritance follow-on now has an explicit acceptance contract in [Scoped rule inheritance](rules/SCOPED_RULE_INHERITANCE.md): it must preserve temporal customer-property links, resolve equally-specific rule conflicts explicitly and prove RLS before any API/UI exposure.
  an action created from a property decision can be completed once with an
  explicit Evidence First classification, supporting evidence references,
  timestamp, responsible actor and audit event. The original decision and its
  recommendation remain immutable. Rules are now explicitly `TENANT` or
  `PROPERTY` scoped, with property scope taking precedence and never applying
  to another property. Customer, field/talhão and asset inheritance/precedence
  remains pending; this slice does not claim those broader scopes.
  Farm360 now exposes outcome capture only to `action:write` users; the user supplies an explicit result, classification, timestamp and optional tenant-local evidence identifiers, while the decision and recommendation remain immutable. `ASSET` scope is explicit and takes precedence only in an evaluation requested for that property-linked asset; it never silently applies during property evaluation or turns the registration into a metric. Farm360 exposes that evaluation only to users who hold both `asset:read` and `decision:read`; it requires a persisted asset-registration evidence identifier, is initiated explicitly, and refreshes the immutable property decision history. Customer, field/talhão and broader inheritance remain pending.
- **Objective:** explicit rule applicability across sector, customer, property,
  field/talhão and asset, with versioning, conflict handling and feedback.
- **Business value:** safely turns asset/context data into recommendations,
  alerts and opportunities rather than a disconnected inventory.
- **Required data:** scope, evidence references, action owner/status and result
  or closure evidence.
- **Dependencies:** Digital Twin asset/context foundation.
- **Evidence First gate:** incomplete scoped evidence remains inconclusive.
- **Security gate:** approval segregation and tenant authorization for rule
  publication, assignment and outcome closure.
- **Tests:** inheritance precedence, RLS, conflicts, version snapshots, audit.
- **Completion criteria:** one factual, non-automated rule completes the core
  chain including a recorded result.

### 3. Flood-event evidence, exposure and hypothesis foundation

- **Status:** foundation in progress. The persisted September event now has a
  factual profile and distinct H1–H4 hypotheses; a tenant assessment can only
  calculate property/asset intersection from a verified `FLOOD_EXTENT` zone.
  Municipal reports, unverified zones, simulated zones, missing subject
  geometry and satellite open-water signals all remain `UNKNOWN` for tenant
  exposure. No real flood zone is seeded by this capability.
- **Objective:** generalize the September 2026 Vale do Ribeira event into an
  Evidence-First flood-event capability: factual timeline, independent
  hypotheses, municipal/property/asset exposure and action traceability.
- **Business value:** makes environmental/operational risk actionable for
  customers, prospects, infrastructure and banana context without claiming a
  cause or unsupported flood extent.
- **Required data:** official event references, municipality geometries,
  timestamped rainfall/river/reservoir observations, scene metadata, asset and
  property geometry, and explicit exposure method/version.
- **Dependencies:** Digital Twin context; existing operational-event/rainfall
  persistence; provider contracts for river stage/discharge.
- **Evidence First gate:** distinguish observed event facts, calculated
  exposure, derived satellite signals and causal hypotheses; incomplete data
  stays unknown/inconclusive.
- **Security gate:** global/public event evidence must not disclose tenant
  property/customer geometry, identities or commercial risk to another tenant.
- **Tests:** municipality/property/asset spatial exposure, time-window
  integrity, hypothesis-state transitions, RLS, no-causality regression, source
  provenance and action-result traceability.
- **Completion criteria:** a factual event can produce a tenant-isolated,
  evidence-backed exposure assessment and non-automated recommendation; no
  causal conclusion or flood-loss claim is emitted without support.

## NEXT

### 4. Evidence-backed environment profile and Prospect intake

- **Objective:** build permitted public-territorial and manually confirmed
  prospect/property context.
- **Business value:** lower visit cost and enable explainable prioritization and
  cross-sell without declaring absent data a need.
- **Required data:** legal-basis review, source terms, geometry, freshness,
  references and configurable score model.
- **Dependencies:** Digital Twin, scoped rules, provider registry.
- **Evidence First gate:** missing score inputs yield `UNKNOWN`/incomplete;
  prioritization is not confirmed customer need.
- **Security gate:** LGPD minimization; no abusive personal enrichment.
- **Tests:** provider boundaries, score unknown policy, evidence-required
  opportunity, RLS and authorization.
- **Completion criteria:** reviewable opportunity without fabricated contacts or
  inferred infrastructure.

### 5. Operational telemetry and monitoring ingress

- **Objective:** device/measurement contracts and replay-safe ingestion before
  MQTT/LoRaWAN activation.
- **Business value:** monitored assets, alerts and recommendations for pumps,
  cold rooms, connectivity and energy.
- **Required data:** device identity, asset link, calibrated measurement, time,
  unit, quality and provider provenance.
- **Dependencies:** Digital Twin assets and scoped rules.
- **Evidence First gate:** calibration, clock, quality and transport failures
  stay explicit; no simulated operational data.
- **Security gate:** per-device credentials, tenant binding, replay protection,
  rate limits and external secrets.
- **Tests:** idempotency/replay, unit/range validation, RLS, audit, unavailable
  provider behavior.
- **Completion criteria:** a test-safe measurement drives a non-automated
  alert/action/result through the rule chain.

### 5A. Smart field sensing contract

- **Objective:** tenant-bound, provider-neutral device/measurement contracts
  for soil and weather sensing before live MQTT/LoRaWAN activation.
- **Business value:** enables strategic rather than blanket sensor deployment
  and eventually calibrates spatial Soil Intelligence.
- **Required data:** confirmed sensor asset, property/field relation, depth,
  measurement/unit, calibration, quality, time and communication provenance.
- **Dependencies:** Digital Twin asset links, telemetry ingress and approved
  device/provider contract.
- **Evidence First/security gates:** simulated fixtures remain `SIMULATED`; no
  public unauthenticated ingestion; model estimates never become observations.
- **Tests/completion:** replay, unit, RLS, sensor-to-asset, calibration and
  source-health tests; one safe measurement reaches the shared rule chain.

### 5B. Soil Intelligence, suitability and sampling foundation

- **Objective:** add analysis areas, field/talhão context, management zones,
  sample/lab traceability and preliminary-vs-validated suitability.
- **Business value:** supports Banana Suitability, smart sampling, targeted
  sensors and evidence-backed consulting services.
- **Required data:** verified property/field, explicit non-legal analysis area,
  provider provenance, approved crop policy and later lab/field evidence.
- **Dependencies:** Digital Twin, property-scoped rules, telemetry contracts,
  provider-neutral terrain/soil/remote adapters and shared flood exposure.
- **Evidence First/security gates:** no legal-boundary claim from drawn zones;
  satellite/modelled context cannot become lab/observed data; agronomic disease
  and automated irrigation remain `EXPERT_VALIDATION_REQUIRED`.
- **Tests/completion:** zone version/geometry, sample chain, lab provenance,
  missing uncertainty, RLS and suitability decision/action traceability; a
  `PRELIMINARY_*` result never silently promotes to validated.

### 6. Banana operational-risk and inspection workflow

- **Objective:** combine confirmed field context, weather/telemetry and imagery
  for inspection recommendations, never disease diagnosis.
- **Business value:** banana consulting and recurring monitoring.
- **Required data:** confirmed fields/talhões, crop context, inspections,
  approved agronomic rules and sensor/weather provenance.
- **Dependencies:** fields/assets, telemetry, scoped rules, agronomist policy.
- **Evidence First gate:** satellite alone only creates a risk/triage signal;
  no disease, flooded banana hectares or loss claim without corroboration.
- **Security gate:** tenant isolation and approved-rule publication.
- **Tests:** evidence combination, missing/conflicting evidence, no-diagnosis
  regression, provenance and result capture.
- **Completion criteria:** agronomist-reviewable inspection and closure are
  traceable end-to-end.

## LATER

- Connect feasibility: owned/official POP and tower inventories, DEM-backed
  LoS/Fresnel/link-budget calculations and reviewable commercial action.
- Energy and Security contextual adapters/rules after real source contracts.
- Ribeira Trace after field, asset and operational-event foundations.
- Contextual AI/RAG, next-best-action and automation after permissioned,
  evidence-complete context and evaluation controls.
- Provider-neutral remote-sensing adapters for optional Earth Engine,
  USGS/NASA Landsat 8/9 and JRC datasets after official contracts, licensing,
  comparability policy and opt-in smoke tests are available.
- Customer-facing documentation site, contextual in-product help, training
  delivery tooling, commercial pricing calculator and accounting/unit-economics
  dashboards after their authoritative inputs and operating model exist.

## BLOCKED

- ANA: `AUTH_REQUIRED_PENDING_PROVIDER`; no invented river data.
- SAISP: `NOT_APPROVED_FOR_AUTOMATION`; manual evidence only and fail closed.
- Cloudflare named tunnel: `https://app.ribeiraconecta.com.br` is the active
  HTTPS application origin. API, PostgreSQL, metrics, debug and development
  listeners remain private; no wildcard OIDC trust or direct public port is
  authorized.
- Customer telemetry/MQTT/LoRaWAN: no approved device/provider contract.
- Agronomic disease rules: require approved policy and corroborating data.

## DEFERRED

- Registro S1 V2 raster processing. The selected 06 Sep / 12 Sep 2026 pair
  (IW, descending, relative orbit 126, VV/VH) and validation tile `x10_y355`
  are preserved with 100% common Registro coverage. Processing requires a
  separately authorized bounded increment; other Registro tiles and
  municipalities are not implied.
- Premium imagery, drones, NISAR, ECOSTRESS, EnMAP and model-led automation.

## Operating cadence

For each safe increment: implement → unit/integration test → diff review →
secret check → commit → push feature branch → verify remote hash. A milestone
does not supersede prior evidence or migrations; it adds an explicit successor
record and provenance.
