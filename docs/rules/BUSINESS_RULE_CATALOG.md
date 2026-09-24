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
| Action outcome closure | `IMPLEMENTED` | Tenant-authorized `OPEN` action; explicit result, classification, timestamp, optional tenant evidence and responsible actor retained. Farm360 exposes it only with `action:write`. | migration 029; `test_vertical_slice.py`, `RiskDecisionPanel.test.tsx`. |
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

## Farm360 outcome workflow

An operator with `action:write` opens an `OPEN` action in the authenticated
property workspace and records the result text, its epistemic classification and
the time it was recorded. Outcome evidence identifiers are optional because a
manual confirmation may itself be the available result, but any supplied
identifier is validated as tenant-local by the API. The browser never copies
the decision evidence into the outcome automatically: evidence that supported a
recommendation is not necessarily evidence that the action produced a result.

The API persists the original decision and recommendation unchanged, completes
the action once, records the responsible authenticated actor, and emits
`ACTION_OUTCOME_RECORDED` audit evidence. A failed submission leaves the action
open and displays no fabricated completion. Users without `action:write` can
read the persisted decision history but cannot see or invoke the completion
control.
