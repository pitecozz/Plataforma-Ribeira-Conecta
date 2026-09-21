# Platform flows

These diagrams are version-controlled conceptual flows. They describe intended
boundaries; they do not assert that every planned adapter, UI or automation is
implemented.

## System and module relationships

```mermaid
flowchart TB
  UI[Maps / Farm360 / API] --> APP[Application services]
  APP --> DT[Digital Twin]
  APP --> EV[Evidence and provenance]
  APP --> RE[Rules and decisions]
  RE --> AO[Actions and outcomes]
  APP --> BUS[Business / Prospect]
  DT --> GEO[PostgreSQL/PostGIS with RLS]
  EV --> GEO
  AO --> GEO
  PR[Bounded provider adapters] --> EV
  TEL[Authenticated telemetry adapters] --> EV
```

## Data and decision flow

```mermaid
flowchart LR
  A[Asset] --> B[Timestamped data]
  B --> C[Context and provenance]
  C --> D[Scoped versioned rule]
  D --> E[Decision with limitations]
  E --> F[Human action]
  F --> G[Outcome evidence and audit]
```

## Digital Twin hierarchy

```mermaid
flowchart TD
  T[Tenant] --> C[Customer or prospect]
  C --> P[Verified property]
  P --> F[Field / talhão]
  P --> A[Physical asset]
  F --> Z[Derived management zone]
  A --> S[Sensor or station]
  P --> AA[User analysis area]
  AA -. not a legal boundary .-> L[No cadastral or title claim]
```

## Provider and telemetry flows

```mermaid
flowchart LR
  R[Explicit dataset request] --> P[Provider-neutral port]
  P --> C[CDSE / GEE / USGS-NASA / JRC adapter]
  C --> M[Dataset/item/source metadata]
  M --> E[Provenance and quality outcome]
  E --> D[Decision context]
```

```mermaid
flowchart LR
  S[Sensor] --> N[LoRaWAN / NB-IoT / LTE / Wi-Fi]
  N --> G[Gateway or provider]
  G --> I[Authenticated MQTT / HTTPS ingress]
  I --> O[Validated tenant observation]
  O --> R[Rule -> decision -> action -> outcome]
```

## Flood, soil and prospect flows

```mermaid
flowchart LR
  R[Rain / river / reservoir / official event facts] --> E[Flood event profile]
  E --> H[Independent H1-H4 hypotheses]
  E --> X[Verified exposure geometry]
  X --> P[Tenant property or asset exposure]
  P --> A[Reviewable recommended action]
```

```mermaid
flowchart LR
  B[Terrain / baseline / remote context] --> Z[Management or analysis zone]
  F[Field sensor / inspection] --> Z
  L[Georeferenced laboratory result] --> Z
  Z --> S[Preliminary or validated suitability]
  S --> A[Sampling, inspection or other recommended action]
```

```mermaid
flowchart LR
  P[Permitted prospect context] --> Q[Evidence-backed qualification]
  Q --> O[Reviewable opportunity]
  O --> S[Applicable service]
  S --> C[Proposal / onboarding]
```

Satellite, modelled, sensor, laboratory and manual inputs retain their own
classification throughout each flow. A provider failure, a suggested sample
location or a causal hypothesis cannot be emitted as a factual conclusion.
