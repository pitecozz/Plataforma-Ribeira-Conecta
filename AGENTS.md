# Ribeira Conecta — Autonomous Delivery Rules

This file defines the mandatory operating rules for every AI coding agent,
autonomous development cycle, refactor, implementation, test, documentation
update and architectural change performed in this repository.

These rules are not suggestions.

They exist to keep Ribeira Conecta coherent while autonomous development
continues for long periods without direct human supervision.

---

# 1. Product Mission

Ribeira Conecta is an operational intelligence platform for rural properties,
agriculture, territorial intelligence, environmental context, flood
intelligence, Digital Twin, telemetry and decision support.

The platform must transform heterogeneous observations into traceable,
actionable operational intelligence.

The canonical product chain is:

```text
asset
  ->
data
  ->
context
  ->
rule
  ->
decision
  ->
action
  ->
result
```

Every meaningful platform capability should strengthen this chain or clearly
support one of its stages.

Do not build disconnected demonstrations.

Do not optimize for visual complexity, number of screens, number of features,
or apparent completion percentage.

Optimize for a usable, traceable and operational product.

---

# 2. Product Invariant

Before implementing a feature, ask:

```text
What asset does this concern?
What data supports it?
What context changes its interpretation?
Which rules apply?
What decision can result?
What action can follow?
How is the result observed?
```

A dashboard, map layer, model, integration, score, alert or visualization that
cannot participate in this operational chain must either:

1. have a clearly documented supporting purpose; or
2. expose its current limitation explicitly.

Do not create isolated functionality merely because it looks useful.

---

# 3. Priority Hierarchy

Development priority is determined by operational value and dependencies.

Default priority order:

1. correctness and data integrity
2. security and tenant isolation
3. pilot blockers
4. broken production-critical workflows
5. core operational workflows
6. evidence/provenance
7. shared architectural foundations
8. customer-facing functionality
9. flood intelligence
10. geospatial and Digital Twin capabilities
11. agriculture and soil intelligence
12. integrations and telemetry
13. automation
14. usability improvements
15. performance improvements
16. parity / convenience features
17. cosmetic improvements

This ordering is contextual, not absolute.

A lower category may become more important when it blocks several higher-value
capabilities.

Do not prioritize a visually impressive map feature over a broken core
workflow, missing provenance, security defect, pilot blocker or critical data
problem.

---

# 4. Canonical Documentation

Before selecting substantial work, read:

```text
docs/CODEX_AUTONOMOUS_DELIVERY.md
docs/PILOT_READINESS.md
docs/README.md
```

Then inspect the canonical documents relevant to the task under:

```text
docs/product/
docs/requirements/
docs/geospatial/
docs/data/
docs/provenance/
docs/domain/
docs/rules/
docs/agro/
docs/iot/
docs/integrations/
docs/security/
docs/architecture/
docs/contracts/
docs/operations/
docs/pilot/
docs/business/
docs/commercial/
```

Do not create a new canonical document when an existing canonical document
already owns the subject.

Prefer updating existing documentation over creating competing sources of
truth.

Preserve historical decisions when relevant.

If a decision is superseded, mark it as superseded and explain applicability
instead of silently deleting historical evidence.

---

# 5. Evidence First

Never fabricate:

- observations
- sensor values
- satellite observations
- flood conditions
- rainfall
- river levels
- coverage
- contacts
- customer facts
- property facts
- asset facts
- diagnoses
- confidence
- provider availability
- data freshness
- business needs
- model results
- source reliability

Unknown information remains unknown.

Use the project's explicit scientific/evidence states where available.

Examples:

```text
UNKNOWN
INCONCLUSIVE
OBSERVED
INFERRED
MODELLED
CONFIRMED
```

Do not silently convert missing information into assumptions.

---

# 6. Provenance Is Mandatory

Externally sourced or derived information must preserve applicable provenance.

Record where relevant:

```text
provider
source
source identifier
reference/acquisition timestamp
ingestion timestamp
spatial resolution
temporal resolution
CRS
transformation
processing method
rule version
model version
confidence / quality
limitations
license / use constraints
scope
tenant
property
talhão
asset
```

Derived information must remain traceable to its inputs.

Never display derived information as raw observation.

---

# 7. Scientific and Agronomic Discipline

Satellite-derived information is not automatically an agronomic diagnosis.

Remote sensing may provide evidence such as:

```text
vegetation condition
spectral changes
possible stress
moisture-related indicators
surface changes
temporal anomalies
```

It must not be silently presented as:

```text
confirmed disease
confirmed nutrient deficiency
confirmed pest
confirmed soil diagnosis
```

unless supporting evidence permits that conclusion.

Expose uncertainty and limitations.

---

# 8. Flood Intelligence Discipline

Flood analysis must separate distinct evidence classes.

Where applicable, represent separately:

```text
rainfall
upstream rainfall
river level
reservoir level
reservoir operations
dam/gate operations
soil saturation
terrain
basin characteristics
river geometry
historical events
ENSO / climate context
observed flooding
forecast information
```

Temporal association is not proof of causality.

Do not transform correlation into a causal statement without sufficient
evidence.

Causal hypotheses require explicit evidence states.

Existing provider restrictions remain authoritative.

In particular:

```text
SAISP automation:
NOT_APPROVED_FOR_AUTOMATION
fail closed

ANA:
AUTH_REQUIRED_PENDING_PROVIDER
```

Do not silently bypass these restrictions.

---

# 9. Geospatial Capability Invariant

Ribeira Conecta is NOT a Google Earth clone.

Google Earth is a capability reference for the geospatial experience, not the
identity of the product and not an implementation dependency.

The primary product mission remains:

```text
asset -> data -> context -> rule -> decision -> action -> result
```

However, Ribeira Conecta must progressively provide the relevant capabilities
users expect from a Google-Earth-class geospatial workspace when those
capabilities support the product.

This requirement is mandatory.

It must not replace the operational product roadmap.

---

# 10. Google-Earth-Class Capability Target

The geospatial workspace should progressively support applicable capabilities
including:

## Navigation

- 2D map
- 3D globe
- pan
- zoom
- rotation
- tilt / pitch
- fly-to navigation
- coordinate display
- scale
- fullscreen
- terrain visualization

## Geometry

- Point
- LineString
- Polygon
- MultiPolygon
- property boundaries
- talhões
- operational assets
- infrastructure
- editable geometry
- geometry validation

## Measurements

- distance
- perimeter
- area
- elevation
- elevation profile
- slope where supported

## Terrain

- DEM
- terrain rendering
- altitude
- minimum elevation
- maximum elevation
- mean elevation
- contours
- slope
- aspect
- flow-related terrain analysis where applicable

## Layer management

- enable / disable
- opacity
- ordering
- styling
- legends
- filtering
- system layers
- customer layers
- user-created layers
- source metadata
- temporal metadata

## Search and navigation

- coordinates
- address when provider permits
- municipality
- locality
- property
- customer asset
- geographic feature
- applicable points of interest

## Import / export

- KML
- KMZ
- GeoJSON where useful
- geometry metadata
- style metadata when practical
- validation
- malformed-file handling
- provenance

## Temporal exploration

- imagery/reference date
- historical comparison
- timeline
- temporal layers
- before/after comparisons
- observed changes
- flood-event comparison
- land-cover changes
- vegetation changes where supported

## Satellite and imagery

- usable imagery layers
- acquisition/reference date
- provider
- resolution
- quality information
- cloud information where available
- latest usable observation
- historical imagery where permitted
- automated refresh according to provider availability

## Digital Twin

- property
- talhões
- terrain
- buildings
- roads
- internal infrastructure
- waterways
- drainage
- vegetation
- sensors
- operational assets
- risk zones
- business context
- telemetry overlays
- event overlays

---

# 11. KML Is Optional Input, Not a Dependency

A customer may already have a KML/KMZ created using Google Earth or another
geospatial tool.

Ribeira Conecta should support importing it where applicable.

However:

```text
KML/KMZ MUST NOT be required to use the platform.
```

The platform must also allow users to:

- locate an area
- create a property directly
- draw property boundaries
- edit boundaries
- create talhões
- add points
- add lines
- create assets
- create operational layers
- enrich the Digital Twin

without requiring an external KML file.

Where technically reliable and permitted by the data source, the platform may
assist in generating or suggesting geospatial layers automatically.

Automatic generation must expose uncertainty and must not invent boundaries or
facts.

---

# 12. Google Earth Comparison Discipline

When evaluating a Google Earth capability, classify it using an explicit state
when appropriate:

```text
IMPLEMENT_DIRECTLY
IMPLEMENT_EQUIVALENT
ALREADY_COVERED_BY_RIBEIRA
PLANNED
BLOCKED_BY_DATA
BLOCKED_BY_LICENSE
BLOCKED_BY_PROVIDER
BLOCKED_BY_TECHNOLOGY
NOT_RELEVANT_TO_PRODUCT
```

Do not silently discard relevant capabilities.

Do not create low-value parity work only to increase a feature count.

Do not call geospatial parity complete merely because a 3D globe is displayed.

A visual shell is not a completed capability.

---

# 13. Proprietary Data and Licensing

Never assume that Google-owned or other proprietary assets may be copied,
scraped, redistributed or embedded.

Examples include potentially restricted:

```text
imagery
Street View-like imagery
photogrammetry
3D building assets
terrain products
tiles
proprietary APIs
licensed datasets
```

Use:

- public datasets
- open datasets
- customer-provided datasets
- properly licensed commercial datasets
- officially permitted APIs

when available.

When exact parity depends on unavailable proprietary data, implement an
equivalent workflow where technically and legally appropriate and document the
difference.

---

# 14. Freshness and Satellite Data

Do not interpret "latest imagery" as invented real-time imagery.

"Latest" means:

```text
the latest usable observation available from configured and permitted sources
```

Every imagery-derived layer should expose applicable:

```text
source
acquisition/reference date
ingestion date
resolution
quality
cloud conditions
processing
limitations
```

Prefer automatic refresh where provider access, cost, licensing and operational
constraints permit.

---

# 15. Architecture

Production spatial storage remains PostgreSQL/PostGIS unless an explicitly
approved architecture decision changes it.

Preserve:

- tenant isolation
- forced RLS
- least privilege
- migration integrity
- immutable migration checksums
- explicit contracts
- audit history
- bounded integrations
- provenance
- scoped rules

Do not introduce shadow data stores that silently become alternate sources of
truth.

---

# 16. Tenant Isolation

Every new feature must consider tenant isolation.

Never assume:

```text
tenant A may access tenant B
customer A may access customer B
property A may access property B
```

RLS and application-level authorization must remain aligned.

Never solve development friction by disabling tenant protections.

---

# 17. Rules Engine Discipline

Rules are:

```text
versioned
scoped
traceable
auditable
```

Never silently apply a global rule to a:

- tenant
- customer
- property
- talhão
- sensor
- asset

unless that scope is explicitly intended.

Every important decision generated from rules must be traceable to the rule
version and relevant inputs.

---

# 18. External Integrations

External adapters must be:

- provider-specific
- bounded
- allowlisted where appropriate
- timeout-controlled
- failure-aware
- observable
- fail-closed where required

Never put:

- API keys
- credentials
- OAuth tokens
- passwords
- private keys
- provider secrets

inside source code or browser bundles.

---

# Canonical Application URL and Production Testing

The canonical public application and pilot URL for Ribeira Conecta is:

https://app.ribeiraconecta.com.br

This domain is the authoritative user-facing application origin unless a newer
explicit operator decision changes it.

The autonomous agent IS AUTHORIZED to test the deployed application directly
at:

https://app.ribeiraconecta.com.br

Direct production/pilot validation is encouraged when it helps verify a
deployment, integration, frontend workflow, API behavior, routing, TLS,
Cloudflare access, smoke test or user-visible capability.

Production validation may include, where applicable:

- HTTP/HTTPS reachability
- TLS availability
- redirects
- public frontend loading
- static assets
- documented health endpoints
- documented API endpoints
- authentication entry points
- frontend/backend connectivity
- CORS behavior
- deployment smoke tests
- user-visible navigation
- map loading
- geospatial views
- non-destructive application workflows
- post-deployment health verification

Prefer testing the real deployed URL when validating behavior that can differ
between local development and the deployed application.

Production testing rules:

- Do not replace the canonical domain with temporary Cloudflare Quick Tunnel
  URLs.
- Do not treat localhost URLs as production URLs.
- Development and isolated tests may continue to use localhost/private origins.
- Production-facing links, callbacks, smoke checks and deployment documentation
  should use https://app.ribeiraconecta.com.br when the public origin is
  required.
- Do not hardcode the public domain deep inside application logic when runtime
  configuration is the correct architectural mechanism.
- Historical Quick Tunnel URLs remain obsolete.
- Never expose credentials, tokens, cookies or private headers in logs or
  commits.
- Prefer read-only and non-destructive production checks.
- Tests that create or modify data must use clearly designated test data or a
  test tenant when available and must be safely reversible.
- Never delete, corrupt or mutate real customer data merely to validate a
  feature.
- Never weaken authentication, authorization, tenant isolation, RLS or other
  security controls to make a production test pass.
- A local test passing does not prove production works.
- A production smoke test passing does not replace unit, integration, security
  or build validation.

For production-facing releases, the preferred validation sequence is:

1. run relevant local/unit/integration validation;
2. build the production candidate;
3. perform an isolated candidate smoke test when applicable;
4. deploy/promote according to repository policy;
5. test https://app.ribeiraconecta.com.br directly;
6. verify critical user-visible behavior;
7. retain or restore the known-good release if post-deployment validation
   fails.

The agent may use the canonical URL directly without requesting human approval
for normal non-destructive validation covered by these rules.

---

# 19. Current Operational Restrictions

Do not bypass explicit operator decisions.

Current known constraints include:

```text
Cloudflare:
AUTHORIZED_FOR_PILOT_ACCESS
named tunnel:
https://app.ribeiraconecta.com.br

Historical Quick Tunnel origins:
OBSOLETE

PostgreSQL:
PRIVATE

metrics:
PRIVATE

debug services:
PRIVATE

development services:
PRIVATE

SAISP automation:
NOT_APPROVED_FOR_AUTOMATION
FAIL_CLOSED

ANA:
AUTH_REQUIRED_PENDING_PROVIDER
```

If canonical documentation changes one of these states, follow the newer
explicit documented decision.

---

# 20. Autonomous Development Objective

The autonomous agent exists to move Ribeira Conecta toward a genuinely usable,
tested and deployable platform.

It must NOT optimize for:

- number of commits
- number of generated files
- number of TODOs closed
- visual feature count
- superficial percentage completion
- artificial roadmap progress

The objective is functional delivery.

Never reduce requirements merely to make completion appear higher.

---

# 21. Autonomous Cycle

Before each development cycle:

1. inspect repository status
2. inspect branch
3. read canonical autonomous-delivery guidance
4. inspect relevant documentation
5. inspect recent commits
6. inspect unresolved work
7. identify the highest-impact unblocked task
8. understand dependencies
9. implement the smallest coherent increment
10. run relevant validation
11. review the diff
12. update documentation/state if necessary
13. commit coherent verified work
14. push
15. select the next task

Do not blindly repeat the same action after failure.

---

# 22. Task Selection

Prefer tasks that:

- unblock multiple capabilities
- close pilot blockers
- fix broken workflows
- strengthen shared foundations
- reduce operational risk
- improve traceability
- connect isolated functionality into the operational chain
- turn prototypes into usable workflows
- add tests to unstable critical areas

Avoid spending autonomous cycles polishing low-value UI while higher-impact
work remains blocked.

---

# 23. Definition of Done

A capability is NOT complete merely because code exists.

Use states such as:

```text
NOT_STARTED
PLANNED
IN_PROGRESS
IMPLEMENTED
INTEGRATED
TESTED
VERIFIED
BLOCKED
```

`IMPLEMENTED` is not equivalent to `VERIFIED`.

A major capability is complete only when applicable requirements are covered:

- implementation
- integration
- persistence
- security
- provenance
- user workflow
- failure handling
- tests
- documentation
- operational assumptions
- limitations

---

# 24. Testing Discipline

Before committing, run the relevant subset of:

```text
unit tests
integration tests
contract tests
database tests
geospatial tests
security tests
lint
format checks
type checks
build
smoke tests
secret checks
```

Do not run expensive unrelated suites unnecessarily after every tiny change.

Before declaring a major milestone complete, run broader validation.

Never knowingly commit a broken build as completed work.

---

# 25. Failure Handling

Classify failures before retrying.

## Code failure

Investigate and fix.

## Test failure

Determine whether:

```text
implementation is wrong
test is wrong
environment is wrong
fixture is wrong
contract changed
```

Do not blindly weaken tests.

## Temporary provider/network failure

Retry with bounded exponential backoff.

## Rate limit / quota exhaustion

Do not retry every few seconds forever.

Pause appropriately or use an approved fallback route.

## Authentication failure

Stop repeated attempts and surface the issue.

## Git conflict

Stop automatic destructive operations.

Inspect carefully.

## Production health failure

Keep or restore the known-good version.

---

# 26. Git Discipline

Before changes:

```text
git status
git branch --show-current
```

Never:

- force-push
- rewrite published history
- delete unrelated work
- silently discard user changes
- commit secrets
- push directly to main unless explicitly authorized by repository policy

Prefer small coherent commits.

Examples:

```text
feat(geo): add KML property import validation

feat(flood): add river observation provenance

fix(api): enforce tenant scope on property query

test(geo): cover invalid polygon geometry

docs(data): document satellite acquisition metadata
```

---

# 27. Commit Discipline

A commit should represent one coherent increment.

Do not create meaningless commits such as:

```text
updates
changes
fix stuff
more work
misc
```

The commit should explain what changed.

Only commit when the repository is in a coherent state.

---

# 28. Push Discipline

Commit and push coherent source increments frequently enough to avoid losing
work.

Source delivery and production promotion are separate operations.

A pushed commit does not imply production deployment.

---

# 29. Production Promotion

Promote frontend or backend releases only after applicable checks pass.

For production-facing changes:

1. protected configuration exists
2. relevant tests pass
3. production build succeeds
4. isolated candidate smoke test succeeds
5. promotion occurs
6. post-promotion health check succeeds

If candidate or production health validation fails:

```text
retain or restore known-good release
```

Never knowingly replace a healthy release with a failing build.

---

# 30. Documentation Discipline

A major capability is not complete until its applicable documentation exists.

Document:

- purpose
- workflow
- business rules
- sources
- provenance
- architecture
- security assumptions
- integration behavior
- operational requirements
- known limitations
- tests

If documentation cannot be completed in the same increment, record explicit
documentation debt in the appropriate canonical catalogue.

---

# 31. Digital Twin Discipline

Digital Twin is not merely a 3D visualization.

It should progressively connect:

```text
property
terrain
talhões
infrastructure
water
vegetation
sensors
telemetry
events
rules
risk
decisions
actions
results
```

A Digital Twin object should participate in the operational model whenever
possible.

---

# 32. UI / UX Discipline

User interfaces should expose meaning, not merely data.

Prefer workflows such as:

```text
What happened?
Where?
When?
What evidence supports it?
How certain is it?
Which asset is affected?
Which rule applies?
What action is recommended or required?
What happened after the action?
```

Avoid dashboards consisting only of disconnected counters.

---

# 33. Performance

Geospatial and telemetry workloads must avoid unnecessary full-dataset
transfers.

Prefer where applicable:

- spatial indexes
- viewport queries
- pagination
- tiled rendering
- LOD
- progressive loading
- caching
- bounded queries
- background processing
- precomputation when justified

Do not optimize prematurely at the expense of correctness.

---

# 34. No Fake Completion

Never create fake implementations to satisfy a checklist.

Examples of unacceptable completion:

```text
button exists but does nothing
map control exists without implementation
mock data presented as real
placeholder API treated as integrated
hardcoded success state
empty test that always passes
visual KML button without actual parsing
3D globe counted as complete Digital Twin
```

If functionality is partial, mark it partial.

---

# 35. Preserve Existing Valid Work

Do not rewrite functioning subsystems without a concrete reason.

Before major refactors:

1. understand existing behavior
2. identify the actual problem
3. preserve contracts where possible
4. add tests around critical behavior
5. migrate incrementally

Prefer root-cause fixes over broad rewrites.

---

# 36. Security Stop Conditions

Stop autonomous changes and surface the problem if work would require:

- exposing credentials
- weakening RLS
- disabling authentication
- opening private databases publicly
- making debug services public
- bypassing tenant isolation
- committing secrets
- bypassing an explicit fail-closed integration restriction

Do not "temporarily" weaken these protections merely to make a test pass.

---

# 37. Human Decisions

Do not override explicit human product or operational decisions.

If documentation contains conflicting decisions:

1. identify the conflict
2. determine the newest applicable canonical decision if possible
3. preserve evidence
4. avoid silently choosing an irreversible interpretation

When materially ambiguous and high-risk, stop that specific path and continue
other unblocked work where possible.

---

# 38. Continuous Autonomous Operation

The agent may continue through multiple development cycles without waiting for
human approval when:

- the task is within documented scope
- requirements are sufficiently clear
- the change is reversible through Git
- security invariants remain intact
- tests can validate the result

Do not stop merely because one milestone or one invocation ended.

Continue with the next highest-value unblocked task.

---

# 39. Autonomous Stop Conditions

Stop the autonomous delivery loop only when one of these applies:

```text
project completion criteria are satisfied
critical human decision is required
security boundary blocks safe progress
credentials/authorization are required
repository state cannot be reconciled safely
all meaningful remaining work is externally blocked
operator-defined stop marker is present
```

Do NOT create a stop marker simply because:

- one task finished
- one feature finished
- one commit was pushed
- one invocation ended
- progress is temporarily difficult

---

# 40. Completion Claim

Do not claim Ribeira Conecta is complete based on a percentage alone.

A credible completion assessment should consider:

```text
requirements coverage
operational workflows
pilot readiness
data integrations
geospatial capability
Digital Twin
flood intelligence
agriculture
security
tenant isolation
provenance
tests
deployment
documentation
known blockers
```

If progress percentages are maintained, they must be evidence-backed.

Never inflate progress by subdividing trivial tasks or lowering acceptance
criteria.

---

# 41. Final Operating Principle

When choosing between:

```text
more features
```

and:

```text
a smaller number of features that are integrated, traceable, tested,
operational and useful
```

choose the second.

Ribeira Conecta must become a dependable operational intelligence platform,
not a collection of demos.

Google-Earth-class geospatial capability is an important mandatory platform
capability.

It is not the product's sole purpose.

Always preserve the canonical operational chain:

```text
asset -> data -> context -> rule -> decision -> action -> result
```
