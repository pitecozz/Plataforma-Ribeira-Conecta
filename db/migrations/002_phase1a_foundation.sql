-- Phase 1A foundation. Applied after 001_initial.sql by the migration runner.
-- This file is immutable after application; create a new migration for changes.

CREATE TABLE IF NOT EXISTS identity_user (
  id uuid PRIMARY KEY,
  external_subject text NOT NULL UNIQUE,
  email text,
  display_name text,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS iam_role (
  id uuid PRIMARY KEY,
  code text NOT NULL UNIQUE,
  description text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS iam_permission (
  id uuid PRIMARY KEY,
  code text NOT NULL UNIQUE,
  description text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role_permission (
  role_id uuid NOT NULL REFERENCES iam_role(id),
  permission_id uuid NOT NULL REFERENCES iam_permission(id),
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS tenant_membership (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  user_id uuid NOT NULL REFERENCES identity_user(id),
  role_id uuid NOT NULL REFERENCES iam_role(id),
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id, role_id)
);

CREATE TABLE IF NOT EXISTS service_account (
  id uuid PRIMARY KEY,
  tenant_id uuid REFERENCES tenant(id),
  name text NOT NULL,
  external_subject text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provider_registry (
  provider_id text PRIMARY KEY,
  name text NOT NULL,
  category text NOT NULL,
  authority text NOT NULL,
  endpoint text,
  license text,
  authentication_type text NOT NULL,
  spatial_resolution text,
  temporal_resolution text,
  version text,
  status text NOT NULL,
  last_success timestamptz,
  last_failure timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE observation ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE decision ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS correlation_id text;
ALTER TABLE rule_definition ALTER COLUMN approved_by TYPE text USING approved_by::text;

CREATE UNIQUE INDEX IF NOT EXISTS observation_idempotency_uq
  ON observation (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS decision_idempotency_uq
  ON decision (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS evidence_reference_uq
  ON evidence (tenant_id, reference_id);

-- Replace bootstrap policies with policies that protect reads and writes. The
-- application role is not table owner and FORCE RLS also protects owner usage.
DO $$
DECLARE
  item record;
BEGIN
  DROP POLICY IF EXISTS tenant_isolation ON tenant;
  FOR item IN SELECT * FROM (VALUES
    ('tenant', 'tenant_id_isolation'),
    ('property', 'property_tenant_isolation'),
    ('source', 'source_tenant_isolation'),
    ('observation', 'observation_tenant_isolation'),
    ('evidence', 'evidence_tenant_isolation'),
    ('rule_definition', 'rule_tenant_isolation'),
    ('decision', 'decision_tenant_isolation'),
    ('alert', 'alert_tenant_isolation'),
    ('action', 'action_tenant_isolation'),
    ('audit_log', 'audit_tenant_isolation'),
    ('data_quality_event', 'quality_tenant_isolation'),
    ('tenant_membership', 'membership_tenant_isolation'),
    ('service_account', 'service_account_tenant_isolation')
  ) AS policy_items(table_name, policy_name)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', item.policy_name, item.table_name);
  END LOOP;

  CREATE POLICY tenant_id_isolation ON tenant
    USING (id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY property_tenant_isolation ON property
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY source_tenant_isolation ON source
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY observation_tenant_isolation ON observation
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY evidence_tenant_isolation ON evidence
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY rule_tenant_isolation ON rule_definition
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY decision_tenant_isolation ON decision
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY alert_tenant_isolation ON alert
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY action_tenant_isolation ON action
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY audit_tenant_isolation ON audit_log
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY quality_tenant_isolation ON data_quality_event
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY membership_tenant_isolation ON tenant_membership
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
  CREATE POLICY service_account_tenant_isolation ON service_account
    USING (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true')
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
      OR current_setting('app.platform_admin', true) = 'true');
END
$$;

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant FORCE ROW LEVEL SECURITY;
ALTER TABLE property ENABLE ROW LEVEL SECURITY;
ALTER TABLE property FORCE ROW LEVEL SECURITY;
ALTER TABLE source ENABLE ROW LEVEL SECURITY;
ALTER TABLE source FORCE ROW LEVEL SECURITY;
ALTER TABLE observation ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE rule_definition ENABLE ROW LEVEL SECURITY;
ALTER TABLE rule_definition FORCE ROW LEVEL SECURITY;
ALTER TABLE decision ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision FORCE ROW LEVEL SECURITY;
ALTER TABLE alert ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert FORCE ROW LEVEL SECURITY;
ALTER TABLE action ENABLE ROW LEVEL SECURITY;
ALTER TABLE action FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
ALTER TABLE data_quality_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_quality_event FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_membership FORCE ROW LEVEL SECURITY;
ALTER TABLE service_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_account FORCE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ribeira_app;
