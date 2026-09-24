# Ribeira Conecta documentation portal

This is the canonical navigation point for the repository documentation. The
platform is an Evidence-First operational decision system:

```text
asset -> data -> context -> rule -> decision -> action -> result
```

No document promotes a plan, model, visual layer, provider failure, or missing
input into a fact. `UNKNOWN` and `INCONCLUSIVE` are useful outcomes.

## Navigate by role

| I am… | Start here |
|---|---|
| a developer | [architecture](architecture/ARCHITECTURE.md), [domain model](domain/DOMAIN_MODEL.md), [local development](operations/LOCAL_DEVELOPMENT.md), [delivery plan](CODEX_AUTONOMOUS_DELIVERY.md) |
| an operator or support analyst | [runbook](operations/RUNBOOK.md), [automatic property refresh](geospatial/AUTOMATIC_PROPERTY_REFRESH.md), [data quality](data/DATA_QUALITY.md), [provenance](provenance/PROVENANCE.md), [provider catalogue](integrations/README.md) |
| a producer or customer | [module catalogue](product/MODULE_CATALOG.md), [service catalogue](product/SERVICE_CATALOG.md), [learning path](training/LEARNING_PATH.md) |
| a consultant or agronomic partner | [Soil Intelligence](agro/SOIL_INTELLIGENCE.md), [agricultural suitability](agro/AGRICULTURAL_SUITABILITY.md), [smart sampling](agro/SMART_SOIL_SAMPLING.md), [Evidence First training](training/LEARNING_PATH.md#evidence-first) |
| commercial | [service packaging](commercial/SERVICE_PACKAGING.md), [pricing model](commercial/PRICING_MODEL.md), [customer journey](commercial/SERVICE_PACKAGING.md#customer-journey-and-onboarding) |
| an auditor | [feature catalogue](product/FEATURE_CATALOG.md), [business rule catalogue](rules/BUSINESS_RULE_CATALOG.md), [data catalogue](data/DATA_CATALOG.md), [provenance](provenance/PROVENANCE.md) |

## Canonical catalogues

- [Feature catalogue](product/FEATURE_CATALOG.md): lifecycle, evidence, security,
  delivery and commercial status of capabilities.
- [Module catalogue](product/MODULE_CATALOG.md): module purpose and boundaries.
- [Service catalogue](product/SERVICE_CATALOG.md): sellable-service hypotheses
  and automation/expert boundaries.
- [Business rule catalogue](rules/BUSINESS_RULE_CATALOG.md): auditable rule
  metadata and validation status.
- [Data catalogue](data/DATA_CATALOG.md) and
  [source catalogue](data/SOURCE_CATALOG.md): canonical entities and sources.
- [Integration catalogue](integrations/README.md): provider contracts and
  failure/fallback policy.
- [Platform flows](architecture/PLATFORM_FLOWS.md): version-controlled system,
  provider, telemetry, flood, soil and prospect diagrams.
- [Pilot Quick Start](training/PILOT_QUICK_START.md): currently available beta
  workflow and safe interpretation boundaries.

## Documentation quality gate

Major code changes must update the relevant catalogue and detailed document in
the same milestone when practical. The author checks internal links, required
feature metadata, duplicate feature IDs, Mermaid source where added, `git diff
--check`, and a changed-file secret scan. Missing material is recorded in the
feature catalogue's documentation-debt table; it is not silently ignored.

Documentation is versioned with Git. A future documentation site may add
search, navigation, version selection, API references and rendered diagrams,
but no framework is a current dependency.
