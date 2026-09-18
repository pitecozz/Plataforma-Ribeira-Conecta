-- Refuse to discard issuer-aware identities or persistent platform authority.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM identity_user WHERE external_issuer IS NOT NULL OR platform_admin) THEN
    RAISE EXCEPTION 'cannot rollback 014 while OIDC identities or platform admins exist';
  END IF;
  IF EXISTS (
    SELECT 1 FROM identity_user GROUP BY external_subject HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'cannot rollback 014 while external subjects are duplicated';
  END IF;
END $$;
DROP INDEX IF EXISTS tenant_membership_active_identity_idx;
DROP INDEX IF EXISTS identity_user_issuer_subject_uq;
ALTER TABLE identity_user DROP COLUMN IF EXISTS platform_admin;
ALTER TABLE identity_user DROP COLUMN IF EXISTS external_issuer;
ALTER TABLE identity_user ADD CONSTRAINT identity_user_external_subject_key UNIQUE (external_subject);
