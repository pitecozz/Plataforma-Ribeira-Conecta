# Pricing model

## Status vocabulary

| Status | Meaning |
|---|---|
| `DECIDED` | Confirmed product rule already represented in versioned policy; see [business rules](../business/RIBEIRA_BUSINESS_RULES.md). |
| `HYPOTHESIS` | Coherent model proposal, not an offer or active commercial policy. |
| `TO_VALIDATE` | Needs cost, customer, legal or capacity evidence. |
| `UNKNOWN` | Required evidence is absent. |

## Current position

- `DECIDED`: historical pricing-policy mechanics and incomplete-pricing behavior
  are implemented and versioned; they are not a universal current market price.
- `HYPOTHESIS`: hybrid onboarding + subscription + optional consulting/add-ons.
- `TO_VALIDATE`: package bands, regional willingness to pay, support levels,
  area/device/report dimensions, hardware model and margins.
- `UNKNOWN`: final BRL prices, customer-specific terms, field/lab costs and
  sustainable margins until actual evidence is supplied.

Pricing should be simple, predictable, modular, scalable, transparent and
margin-aware. It should consider customer segment, property-count or area
bands, active modules, refresh/report frequency, devices/telemetry, support
level, API/advanced processing use and field work. Area need not scale linearly:
small/medium/large/enterprise bands may be more defensible than a per-hectare
multiplier. Invoices must not become unpredictable micro-charges.

Hardware options — customer purchase, lease/rental, hardware-as-a-service or
project-included — remain `TO_VALIDATE` against replacement, warranty,
maintenance, connectivity, battery, inventory and support responsibility.

See [service packaging](SERVICE_PACKAGING.md) and [cost model](COST_MODEL.md).
