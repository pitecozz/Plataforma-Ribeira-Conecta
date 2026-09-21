# Business rule catalogue

This is the canonical human-readable catalogue for production and proposed
rules. The executable/versioned record remains the authority for a decision;
this document never rewrites historical policy.

## Required rule metadata

Every rule has a stable ID, name/description, scope (tenant, customer,
property, field, zone, asset or crop), tenant applicability, inputs,
conditions, output/decision/recommended action, evidence requirements, source
of business/agronomic policy, expert-validation state, version, effective and
retirement dates, and test/documentation links. A rule with missing mandatory
evidence returns `UNKNOWN` or `INCONCLUSIVE`; it does not default to false.

| Rule family | Current state | Scope / constraints | Canonical detail |
|---|---|---|---|
| Versioned decision rules | `IMPLEMENTED` | `TENANT` and `PROPERTY`; property precedence is explicit. | `engine.py`, `service.py`, migration 031. |
| Action outcome closure | `IMPLEMENTED` | Tenant-authorized action; evidence/classification and responsible actor retained. | migration 029; `test_vertical_slice.py`. |
| Commercial opportunity qualification | `IMPLEMENTED` | Valid tenant evidence required; unknown does not create opportunity. | [Business rules](../business/RIBEIRA_BUSINESS_RULES.md), `business.py`. |
| Flood exposure assessment | `FOUNDATION` | Only verified flood extent and tenant geometry can calculate exposure. | migration 030; H1–H4 are hypotheses, not causal arrows. |
| Suitability / irrigation / banana policies | `PLANNED` | Must be scoped and expert-approved where agronomic. | `EXPERT_VALIDATION_REQUIRED`; see [Agro docs](../agro/AGRICULTURAL_SUITABILITY.md). |

## Rule-to-outcome flow

```mermaid
flowchart LR
  A[Scoped asset/context] --> B[Versioned evidence]
  B --> C[Applicable rule]
  C --> D[Decision with limitations]
  D --> E[Recommended human action]
  E --> F[Outcome evidence and audit]
```
