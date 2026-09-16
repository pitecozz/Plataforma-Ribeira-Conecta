# ADR-0010: Controlled raster worker and local object storage

- Status: accepted
- Date: 2026-09-16

## Decision

Represent raster work as idempotent `ProcessingJob` records and run a bounded
local worker in this phase. Keep object storage behind `ObjectStoragePort`; use
the development-only `LocalObjectStorage` implementation.

## Rationale

NDVI can require remote asset transfer and raster CPU/memory, so it must not
block scene-search HTTP requests. The job key combines scene, property,
algorithm version and parameters. This supports retries and future queue
workers without changing the domain.

## Consequences

Production deployment still needs an authenticated object-store adapter, an
asset download policy, queue execution and resource quotas. Missing CDSE asset
credentials remains an explicit `ASSET_UNAVAILABLE` result.
