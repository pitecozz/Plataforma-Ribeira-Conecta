# Scoped rule inheritance

**Status:** `PARTIAL` — tenant, property, explicit asset, explicit
field/talhão and customer scope are implemented. Zone and crop scope remain
deliberately unavailable.

## Current safe precedence

An evaluation uses the most specific applicable active rule:

```text
asset (only during an explicit asset evaluation)
-> field/talhão (only during an explicit field evaluation)
-> property
-> customer
-> tenant
```

An asset registration establishes only sourced asset facts and its use as
applicability context. It is not an observation, calibration, condition,
coverage result or diagnosis. Property-only evaluations never consume an
asset-scoped rule.

A field/talhão registration establishes only sourced, non-legal operational
context inside a property. It is not title/survey, crop, soil, laboratory,
management-zone or agronomic evidence. Property-only evaluations never consume a
field-scoped rule; it is selected only by explicit field evaluation, and the
decision retains `FIELD_REGISTRATION` evidence plus `subject_field_id`.

## Customer-scope guarantees

Customer-scoped rules are available through the versioned rule endpoint and are
valid only when all of the following are true:

- the rule references a tenant-local customer through a composite database key;
- the evaluated property has an explicit, active `customer_property` link at
  evaluation time (`valid_from <= now < valid_until`, or no end time);
- a missing, expired or cross-tenant link makes the customer rule inapplicable;
- precedence is deterministic:
  `asset -> field/talhão -> property -> customer -> tenant`;
- equally specific active rules do not fall back to insertion order or version:
  evaluation returns an explicit `CONFLICTING` decision for human resolution;
- each decision and its audit event retain the selected scope and, for customer
  scope, the linked customer identifier as immutable applicability context;
- PostgreSQL migration 038 enforces tenant-local customer references and guards
  decision context against a missing active customer/property link.

The customer-property relationship is applicability context only. It does not
prove legal ownership, a confirmed business need, service availability or an
agronomic conclusion. No Farm360 rule-creation UI is introduced by this slice;
the authorized API remains the operational surface.

## Documentation debt

Zone/crop inheritance remains a separate dependency: versioned management-zone,
crop/context models and approved agronomic policy must exist first. A customer
or field rule-creation UI remains future work; the authorized API is the current
operational surface.
