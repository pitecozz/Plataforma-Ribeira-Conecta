-- Phase 1F: an auditable temporal delta has two upstream derived products.
CREATE TABLE IF NOT EXISTS derived_product_dependency (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  derived_product_id uuid NOT NULL,
  upstream_product_id uuid NOT NULL,
  relationship text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, derived_product_id, relationship),
  UNIQUE (tenant_id, derived_product_id, upstream_product_id),
  FOREIGN KEY (tenant_id, derived_product_id) REFERENCES derived_product(tenant_id, id),
  FOREIGN KEY (tenant_id, upstream_product_id) REFERENCES derived_product(tenant_id, id),
  CHECK (relationship IN ('BASELINE_NDVI', 'TARGET_NDVI')),
  CHECK (derived_product_id <> upstream_product_id)
);
CREATE INDEX IF NOT EXISTS derived_product_dependency_upstream_idx
  ON derived_product_dependency (tenant_id, upstream_product_id);
ALTER TABLE derived_product_dependency ENABLE ROW LEVEL SECURITY;
ALTER TABLE derived_product_dependency FORCE ROW LEVEL SECURITY;
CREATE POLICY derived_product_dependency_tenant_isolation ON derived_product_dependency
  USING (tenant_id::text = current_setting('app.tenant_id', true) OR current_setting('app.platform_admin', true) = 'true')
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true) OR current_setting('app.platform_admin', true) = 'true');
