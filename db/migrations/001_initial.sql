-- Production target schema. Requires PostgreSQL + PostGIS.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS tenant (
  id uuid PRIMARY KEY,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS property (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  name text NOT NULL,
  geometry geometry(Geometry, 4326),
  geometry_crs text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS property_geometry_gix ON property USING gist (geometry);
CREATE INDEX IF NOT EXISTS property_tenant_idx ON property (tenant_id);

CREATE TABLE IF NOT EXISTS source (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  name text NOT NULL,
  source_type text NOT NULL,
  provider text NOT NULL,
  original_reference text,
  endpoint text,
  source_version text,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observation (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL REFERENCES property(id),
  source_id uuid NOT NULL REFERENCES source(id),
  metric text NOT NULL,
  value numeric,
  unit text,
  observation_timestamp timestamptz NOT NULL,
  ingestion_timestamp timestamptz NOT NULL,
  processing_timestamp timestamptz,
  data_classification text NOT NULL,
  quality_flag text NOT NULL,
  dataset_version text,
  spatial_resolution text,
  temporal_resolution text,
  crs text,
  raw_data_reference text,
  checksum text
);
CREATE INDEX IF NOT EXISTS observation_property_metric_idx ON observation (tenant_id, property_id, metric, observation_timestamp);

CREATE TABLE IF NOT EXISTS evidence (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  evidence_type text NOT NULL,
  reference_id uuid NOT NULL,
  source_id uuid REFERENCES source(id),
  observed_at timestamptz,
  data_classification text NOT NULL,
  transformation text,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rule_definition (
  id uuid NOT NULL,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  version integer NOT NULL,
  name text NOT NULL,
  authority text NOT NULL,
  metric text NOT NULL,
  operator text NOT NULL,
  threshold numeric NOT NULL,
  unit text NOT NULL,
  severity text NOT NULL,
  status text NOT NULL,
  approved_by uuid,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS decision (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL REFERENCES property(id),
  conclusion text NOT NULL,
  data_classification text NOT NULL,
  status text NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  rule_id uuid,
  rule_version integer,
  model_id uuid,
  model_version text,
  confidence numeric,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_data jsonb NOT NULL DEFAULT '[]'::jsonb,
  conflicts jsonb NOT NULL DEFAULT '[]'::jsonb,
  recommended_action jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL REFERENCES property(id),
  alert_type text NOT NULL,
  severity text NOT NULL,
  status text NOT NULL,
  title text NOT NULL,
  decision_id uuid NOT NULL REFERENCES decision(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  action_type text NOT NULL,
  status text NOT NULL,
  responsible_user_id uuid,
  deadline timestamptz,
  decision_id uuid NOT NULL REFERENCES decision(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  actor text NOT NULL,
  event_type text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS data_quality_event (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid REFERENCES property(id),
  source_id uuid REFERENCES source(id),
  event_type text NOT NULL,
  details jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Tenant isolation policy is mandatory in production. The application role must
-- set app.tenant_id per transaction; no table is readable without that setting.
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE property ENABLE ROW LEVEL SECURITY;
ALTER TABLE source ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE rule_definition ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert ENABLE ROW LEVEL SECURITY;
ALTER TABLE action ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_quality_event ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant
  USING (id::text = current_setting('app.tenant_id', true))
  WITH CHECK (id::text = current_setting('app.tenant_id', true));
CREATE POLICY property_tenant_isolation ON property
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY source_tenant_isolation ON source
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY observation_tenant_isolation ON observation
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY evidence_tenant_isolation ON evidence
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY rule_tenant_isolation ON rule_definition
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY decision_tenant_isolation ON decision
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY alert_tenant_isolation ON alert
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY action_tenant_isolation ON action
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY audit_tenant_isolation ON audit_log
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
CREATE POLICY quality_tenant_isolation ON data_quality_event
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
