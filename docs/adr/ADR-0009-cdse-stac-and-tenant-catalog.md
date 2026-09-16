# ADR-0009: CDSE STAC adapter and tenant-scoped scene catalog

- Status: accepted
- Date: 2026-09-16

## Decision

Use a small defensive HTTP adapter for the official CDSE STAC API, behind
`GeospatialProviderPort`. Keep provider/collection metadata global, while
copying discovered scenes and assets into tenant-scoped tables with RLS.

## Rationale

The operation is a bounded JSON search and does not need a full STAC SDK yet.
The adapter has explicit endpoint, redirect, response-size, pagination, timeout,
provider-host and SSRF controls. Tenant-scoped scene copies make Evidence,
audit, licensing decisions and deletion/isolation explicit; global deduplication
can be introduced later only with a documented licensing and access model.

## Consequences

Raw pages are preserved through an object reference. Scene duplication across
tenants is possible and intentional in this phase. Asset downloads require a
separate policy and are not implicit.
