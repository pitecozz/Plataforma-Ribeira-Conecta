DROP TABLE IF EXISTS service_account, tenant_membership, role_permission,
  iam_permission, iam_role, identity_user, provider_registry CASCADE;
DROP INDEX IF EXISTS observation_idempotency_uq, decision_idempotency_uq, evidence_reference_uq;
ALTER TABLE observation DROP COLUMN IF EXISTS idempotency_key;
ALTER TABLE decision DROP COLUMN IF EXISTS idempotency_key;
ALTER TABLE audit_log DROP COLUMN IF EXISTS request_id;
ALTER TABLE audit_log DROP COLUMN IF EXISTS correlation_id;
