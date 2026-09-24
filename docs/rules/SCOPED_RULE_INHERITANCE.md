# Scoped rule inheritance

**Status:** `PARTIAL` — tenant, property and explicit asset scope are implemented.
Customer and field/talhão scope remain deliberately unavailable.

## Current safe precedence

An evaluation uses the most specific applicable active rule:

```text
asset (only during an explicit asset evaluation) -> property -> tenant
```

An asset registration establishes only sourced asset facts and its use as
applicability context. It is not an observation, calibration, condition,
coverage result or diagnosis. Property-only evaluations never consume an
asset-scoped rule.

## Customer-scope acceptance contract

Customer scope may be introduced only as a forward migration when all of these
conditions are met:

- the rule references a tenant-local customer by a composite tenant key;
- applicability is derived solely from an explicit `customer_property` link;
- the link is active at evaluation time (`valid_from <= now < valid_until`, or
  an absent end time), preserving historical links rather than mutating them;
- a missing, expired or cross-tenant link makes the customer rule inapplicable;
- the deterministic precedence is `asset -> property -> customer -> tenant`;
- multiple equally specific active rules produce an explicit conflict or are
  rejected at publication—selection may never depend on insertion order;
- the decision/audit payload preserves selected scope and linked customer ID;
- PostgreSQL RLS, composite foreign keys, SQLite contract tests and API
  authorization tests prove tenant isolation.

The customer-property relationship is applicability context only. It does not
prove legal ownership, a confirmed business need, service availability or an
agronomic conclusion.

## Documentation debt

A customer-scoped rule API/UI is not exposed until the above conflict policy,
forward migration and PostGIS/RLS regression tests are delivered together.
Field/talhão scope remains a separate dependency: a versioned non-legal field
model and its tenant-scoped relationship to a property must exist first.
