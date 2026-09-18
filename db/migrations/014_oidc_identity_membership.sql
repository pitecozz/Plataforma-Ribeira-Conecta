-- Production OIDC identities are stable issuer + subject pairs.  Existing
-- legacy identities retain NULL issuer and are deliberately not auto-mapped.
ALTER TABLE identity_user ADD COLUMN IF NOT EXISTS external_issuer text;
ALTER TABLE identity_user ADD COLUMN IF NOT EXISTS platform_admin boolean NOT NULL DEFAULT false;

ALTER TABLE identity_user DROP CONSTRAINT IF EXISTS identity_user_external_subject_key;
CREATE UNIQUE INDEX IF NOT EXISTS identity_user_issuer_subject_uq
  ON identity_user(external_issuer, external_subject)
  WHERE external_issuer IS NOT NULL;
CREATE INDEX IF NOT EXISTS tenant_membership_active_identity_idx
  ON tenant_membership(user_id, tenant_id)
  WHERE status = 'ACTIVE';
