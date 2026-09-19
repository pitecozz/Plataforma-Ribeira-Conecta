-- Immutable property-boundary provenance and tenant portfolio support.
ALTER TABLE property ADD COLUMN IF NOT EXISTS boundary_checksum text;
ALTER TABLE property ADD COLUMN IF NOT EXISTS updated_at timestamptz;

CREATE TABLE IF NOT EXISTS property_boundary_version (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  geometry geometry(Geometry, 4326) NOT NULL,
  geometry_crs text NOT NULL,
  boundary_source text NOT NULL,
  data_classification text NOT NULL,
  checksum text NOT NULL,
  reason text,
  actor text,
  effective_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, property_id, version),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id)
);
CREATE INDEX IF NOT EXISTS property_boundary_version_lookup_idx
  ON property_boundary_version (tenant_id, property_id, version DESC);
CREATE INDEX IF NOT EXISTS property_boundary_version_geometry_gix
  ON property_boundary_version USING gist (geometry);

ALTER TABLE property_boundary_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_boundary_version FORCE ROW LEVEL SECURITY;
CREATE POLICY property_boundary_version_tenant_isolation ON property_boundary_version
  USING (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true')
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true');
GRANT SELECT, INSERT, UPDATE, DELETE ON property_boundary_version TO ribeira_app;
