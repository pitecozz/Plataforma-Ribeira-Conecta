-- Phase 1B: business domain and Ribeira commercial rule foundation.
-- Immutable after application. Follow-up changes require a new migration.

-- Required before opportunity_evidence can reference the tenant-scoped evidence key.
ALTER TABLE evidence ADD CONSTRAINT evidence_tenant_id_uq UNIQUE (tenant_id, id);

CREATE TABLE IF NOT EXISTS customer (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  customer_type text NOT NULL,
  display_name text NOT NULL,
  legal_name text,
  status text NOT NULL,
  data_classification text NOT NULL,
  external_reference text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS customer_property (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  customer_id uuid NOT NULL,
  property_id uuid NOT NULL,
  relationship_type text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customer(tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS product (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  sku text,
  name text NOT NULL,
  category text NOT NULL,
  status text NOT NULL,
  description text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS service (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  product_id uuid,
  name text NOT NULL,
  category text NOT NULL,
  status text NOT NULL,
  recurring boolean NOT NULL DEFAULT false,
  revenue_type text NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, product_id) REFERENCES product(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS service_plan (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  service_id uuid NOT NULL,
  name text NOT NULL,
  billing_period text NOT NULL,
  monthly_price numeric(19,4),
  currency text NOT NULL,
  status text NOT NULL,
  revenue_treatment text NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, service_id) REFERENCES service(tenant_id, id),
  CHECK (monthly_price IS NULL OR monthly_price >= 0)
);

CREATE TABLE IF NOT EXISTS customer_contract (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  customer_id uuid NOT NULL,
  property_id uuid,
  contract_type text NOT NULL,
  counterparty_name text,
  external_provider_name text,
  ribeira_revenue_treatment text NOT NULL,
  status text NOT NULL,
  start_at timestamptz NOT NULL,
  end_at timestamptz,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customer(tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS contract_version (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  contract_id uuid NOT NULL,
  version integer NOT NULL,
  status text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  total_price numeric(19,4),
  currency text NOT NULL,
  recurring boolean NOT NULL DEFAULT false,
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  approved_by text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, contract_id, version),
  FOREIGN KEY (tenant_id, contract_id) REFERENCES customer_contract(tenant_id, id),
  CHECK (total_price IS NULL OR total_price >= 0)
);

CREATE TABLE IF NOT EXISTS subscription (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  contract_id uuid NOT NULL,
  contract_version_id uuid NOT NULL,
  service_plan_id uuid NOT NULL,
  status text NOT NULL,
  start_at timestamptz NOT NULL,
  end_at timestamptz,
  monthly_price numeric(19,4),
  currency text NOT NULL,
  recurring boolean NOT NULL,
  mrr_eligible boolean NOT NULL,
  revenue_treatment text NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, contract_id) REFERENCES customer_contract(tenant_id, id),
  FOREIGN KEY (tenant_id, contract_version_id) REFERENCES contract_version(tenant_id, id),
  FOREIGN KEY (tenant_id, service_plan_id) REFERENCES service_plan(tenant_id, id),
  CHECK (monthly_price IS NULL OR monthly_price >= 0)
);

CREATE TABLE IF NOT EXISTS site (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  name text NOT NULL,
  site_type text NOT NULL,
  geometry geometry(Geometry, 4326),
  geometry_crs text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id)
);
CREATE INDEX IF NOT EXISTS site_geometry_gix ON site USING gist (geometry);

CREATE TABLE IF NOT EXISTS installation_project (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  customer_id uuid NOT NULL,
  property_id uuid,
  name text NOT NULL,
  status text NOT NULL,
  technical_provider_type text NOT NULL,
  customer_total_project_cost numeric(19,4),
  currency text NOT NULL,
  ribeira_revenue_treatment text NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customer(tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  CHECK (customer_total_project_cost IS NULL OR customer_total_project_cost >= 0)
);

CREATE TABLE IF NOT EXISTS asset (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  asset_type text NOT NULL,
  name text NOT NULL,
  serial_number text,
  status text NOT NULL,
  property_id uuid,
  site_id uuid,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (tenant_id, site_id) REFERENCES site(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS asset_ownership (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  asset_id uuid NOT NULL,
  ownership_kind text NOT NULL,
  customer_id uuid,
  purchased_by text,
  maintained_by text,
  replacement_responsibility text,
  risk_bearer text,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  acquisition_document text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, asset_id) REFERENCES asset(tenant_id, id),
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customer(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS installation (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  project_id uuid NOT NULL,
  asset_id uuid,
  status text NOT NULL,
  installed_at timestamptz,
  one_time_revenue numeric(19,4),
  currency text NOT NULL,
  ownership_kind text NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES installation_project(tenant_id, id),
  FOREIGN KEY (tenant_id, asset_id) REFERENCES asset(tenant_id, id),
  CHECK (one_time_revenue IS NULL OR one_time_revenue >= 0)
);

CREATE TABLE IF NOT EXISTS capex_item (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  project_id uuid,
  asset_id uuid,
  description text NOT NULL,
  amount numeric(19,4),
  currency text NOT NULL,
  capex_classification text NOT NULL,
  ownership_kind text NOT NULL,
  purchased_by text,
  source text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES installation_project(tenant_id, id),
  FOREIGN KEY (tenant_id, asset_id) REFERENCES asset(tenant_id, id),
  CHECK (amount IS NULL OR amount >= 0)
);

CREATE TABLE IF NOT EXISTS cost_item (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  project_id uuid,
  customer_contract_id uuid,
  cost_type text NOT NULL,
  amount numeric(19,4),
  currency text NOT NULL,
  is_net_margin_component boolean NOT NULL DEFAULT false,
  source text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES installation_project(tenant_id, id),
  FOREIGN KEY (tenant_id, customer_contract_id) REFERENCES customer_contract(tenant_id, id),
  CHECK (amount IS NULL OR amount >= 0)
);

CREATE TABLE IF NOT EXISTS revenue_item (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  project_id uuid,
  customer_contract_id uuid,
  revenue_type text NOT NULL,
  amount numeric(19,4),
  currency text NOT NULL,
  recognized_by_ribeira boolean NOT NULL,
  recurring boolean NOT NULL,
  source text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES installation_project(tenant_id, id),
  FOREIGN KEY (tenant_id, customer_contract_id) REFERENCES customer_contract(tenant_id, id),
  CHECK (amount IS NULL OR amount >= 0)
);

CREATE TABLE IF NOT EXISTS pass_through_item (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  project_id uuid,
  customer_id uuid,
  description text NOT NULL,
  amount numeric(19,4),
  currency text NOT NULL,
  supplier text,
  document_reference text,
  paid_at timestamptz,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES installation_project(tenant_id, id),
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customer(tenant_id, id),
  CHECK (amount IS NULL OR amount >= 0)
);

CREATE TABLE IF NOT EXISTS pricing_policy (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  name text NOT NULL,
  scope text NOT NULL,
  status text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS pricing_policy_version (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  pricing_policy_id uuid NOT NULL,
  version integer NOT NULL,
  status text NOT NULL,
  lower_threshold numeric(19,4) NOT NULL,
  lower_rate numeric(12,8) NOT NULL,
  lower_minimum numeric(19,4) NOT NULL,
  upper_rate numeric(12,8) NOT NULL,
  upper_minimum numeric(19,4) NOT NULL,
  currency text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  created_by text NOT NULL,
  approved_by text,
  data_classification text NOT NULL,
  source text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, pricing_policy_id, version),
  FOREIGN KEY (tenant_id, pricing_policy_id) REFERENCES pricing_policy(tenant_id, id),
  CHECK (lower_threshold >= 0 AND lower_rate >= 0 AND lower_minimum >= 0 AND upper_rate >= 0 AND upper_minimum >= 0)
);

CREATE TABLE IF NOT EXISTS operational_capacity_policy (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  scope text NOT NULL,
  capacity_type text NOT NULL,
  value numeric(19,4) NOT NULL,
  unit text NOT NULL,
  effective_from timestamptz NOT NULL,
  effective_until timestamptz,
  status text NOT NULL,
  created_by text NOT NULL,
  approved_by text,
  source text NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  CHECK (value >= 0)
);

CREATE TABLE IF NOT EXISTS commercial_rule (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  name text NOT NULL,
  authority text NOT NULL,
  status text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS commercial_rule_version (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  commercial_rule_id uuid NOT NULL,
  version integer NOT NULL,
  condition jsonb NOT NULL,
  action jsonb NOT NULL,
  status text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  created_by text NOT NULL,
  approved_by text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, commercial_rule_id, version),
  FOREIGN KEY (tenant_id, commercial_rule_id) REFERENCES commercial_rule(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS commercial_opportunity (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  customer_id uuid NOT NULL,
  property_id uuid,
  opportunity_type text NOT NULL,
  status text NOT NULL,
  classification text NOT NULL,
  score numeric(10,4),
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  rule_id uuid,
  rule_version integer,
  estimated_value numeric(19,4),
  estimated_value_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  outcome text,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customer(tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (tenant_id, rule_id) REFERENCES commercial_rule(tenant_id, id),
  CHECK (score IS NULL OR score >= 0),
  CHECK (estimated_value IS NULL OR estimated_value >= 0)
);

CREATE TABLE IF NOT EXISTS opportunity_evidence (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  opportunity_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  role text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, opportunity_id, evidence_id),
  FOREIGN KEY (tenant_id, opportunity_id) REFERENCES commercial_opportunity(tenant_id, id),
  FOREIGN KEY (tenant_id, evidence_id) REFERENCES evidence(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS prospect_scoring_model (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  name text NOT NULL,
  status text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS prospect_scoring_model_version (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  model_id uuid NOT NULL,
  version integer NOT NULL,
  status text NOT NULL,
  unknown_policy text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  created_by text NOT NULL,
  approved_by text,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, model_id, version),
  FOREIGN KEY (tenant_id, model_id) REFERENCES prospect_scoring_model(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS prospect_scoring_factor (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  model_version_id uuid NOT NULL,
  factor_key text NOT NULL,
  description text NOT NULL,
  condition jsonb NOT NULL,
  points integer NOT NULL,
  unknown_policy text NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, model_version_id) REFERENCES prospect_scoring_model_version(tenant_id, id)
);

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT table_name FROM (VALUES
    ('customer'), ('customer_property'), ('product'), ('service'),
    ('service_plan'), ('customer_contract'), ('contract_version'), ('subscription'),
    ('site'), ('installation_project'), ('asset'), ('asset_ownership'),
    ('installation'), ('capex_item'), ('cost_item'), ('revenue_item'),
    ('pass_through_item'), ('pricing_policy'), ('pricing_policy_version'),
    ('operational_capacity_policy'), ('commercial_rule'),
    ('commercial_rule_version'), ('commercial_opportunity'),
    ('opportunity_evidence'), ('prospect_scoring_model'),
    ('prospect_scoring_model_version'), ('prospect_scoring_factor')
  ) AS tables(table_name)
  LOOP
    EXECUTE format('CREATE POLICY %I ON %I USING (tenant_id::text = current_setting(''app.tenant_id'', true) OR current_setting(''app.platform_admin'', true) = ''true'') WITH CHECK (tenant_id::text = current_setting(''app.tenant_id'', true) OR current_setting(''app.platform_admin'', true) = ''true'')', item.table_name || '_tenant_isolation', item.table_name);
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', item.table_name);
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ribeira_app;
