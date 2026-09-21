# Ribeira Conecta delivery rules

## Product invariant

Every increment must strengthen a traceable operational chain:

```text
asset -> data -> context -> rule -> decision -> action -> result
```

Do not add a dashboard, map layer, score, model, or integration that cannot
participate in that chain or explicitly expose its limitation.

## Evidence First

- Never fabricate observations, coverage, contacts, asset facts, diagnoses,
  confidence, provider availability, or business need.
- Persist and expose source, timestamps, provenance, transformation,
  rule/model version, result, limitations, conflicts, and unknowns.
- Use the project's explicit data classifications and scientific conclusion
  states. Missing input remains `UNKNOWN`/`INCONCLUSIVE`.
- Satellite-derived information is not an agronomic diagnosis on its own.
- For flood incidents, record rainfall, upstream context, river/reservoir
  operations and ENSO separately. Temporal association is not a causal arrow;
  causal hypotheses require explicit evidence states.

## Architecture and security

- Preserve tenant isolation, PostgreSQL/PostGIS as production spatial storage,
  forced RLS, least privilege, audit history, and immutable migration checksums.
- Keep rules versioned and scoped. Do not silently apply a global rule to a
  customer, property, field/talhão, or asset.
- External adapters must be bounded, provider-specific, allowlisted, and fail
  closed. Never add credentials, OAuth tokens, private keys, or browser-exposed
  provider secrets to the repository.
- Do not bypass operator decisions: Cloudflare is `DEFERRED_BY_OPERATOR`;
  SAISP automation is `NOT_APPROVED_FOR_AUTOMATION`/fail-closed; ANA is
  `AUTH_REQUIRED_PENDING_PROVIDER`.

## Delivery discipline

- Read `docs/CODEX_AUTONOMOUS_DELIVERY.md` before choosing the next increment.
- Prefer shared operational foundations with demonstrable business value over
  isolated technical processing work.
- Preserve superseded decisions and data; mark their applicability rather than
  deleting historical evidence.
- Before commit: run relevant tests, diff review, formatting, lint/type checks,
  and a secret check when available. Never force-push, rewrite published
  history, or push to `main`.
