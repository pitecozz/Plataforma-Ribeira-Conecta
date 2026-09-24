-- Non-legal field/talhão context is tenant-scoped, source-backed and versioned.
-- It is not title/survey evidence, crop evidence, or an agronomic conclusion.

CREATE TABLE field_context (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  name text NOT NULL CHECK (btrim(name) <> ''),
  status text NOT NULL CHECK (btrim(status) <> ''),
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  observed_at timestamptz NOT NULL,
  data_classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id)
);
CREATE INDEX field_context_property_idx
  ON field_context(tenant_id, property_id, created_at DESC);

CREATE TABLE field_context_boundary_version (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  field_context_id uuid NOT NULL,
  property_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  geometry geometry(Geometry,4326) NOT NULL,
  geometry_crs text NOT NULL CHECK (geometry_crs IN ('EPSG:4326','CRS:84')),
  geometry_checksum text NOT NULL CHECK (length(geometry_checksum) = 64),
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  observed_at timestamptz NOT NULL,
  data_classification text NOT NULL,
  reason text NOT NULL CHECK (btrim(reason) <> ''),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, field_context_id, version),
  FOREIGN KEY (tenant_id, field_context_id) REFERENCES field_context(tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id)
);
CREATE INDEX field_context_boundary_version_geometry_gix
  ON field_context_boundary_version USING gist(geometry);

CREATE OR REPLACE FUNCTION field_context_boundary_property_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF ST_SRID(NEW.geometry) <> 4326
     OR GeometryType(NEW.geometry) NOT IN ('POLYGON','MULTIPOLYGON')
     OR NOT ST_IsValid(NEW.geometry) THEN
    RAISE EXCEPTION 'field context geometry must be a valid EPSG:4326 Polygon or MultiPolygon'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM property
     WHERE tenant_id=NEW.tenant_id
       AND id=NEW.property_id
       AND geometry IS NOT NULL
       AND ST_Covers(geometry, NEW.geometry)
  ) THEN
    RAISE EXCEPTION 'field context geometry must be contained by a persisted tenant property boundary'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM field_context
     WHERE tenant_id=NEW.tenant_id
       AND id=NEW.field_context_id
       AND property_id=NEW.property_id
  ) THEN
    RAISE EXCEPTION 'field context boundary must match its tenant property'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION field_context_boundary_property_guard() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION field_context_boundary_property_guard() TO ribeira_app;
CREATE TRIGGER field_context_boundary_property_guard
  BEFORE INSERT OR UPDATE ON field_context_boundary_version
  FOR EACH ROW EXECUTE FUNCTION field_context_boundary_property_guard();

ALTER TABLE field_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_context FORCE ROW LEVEL SECURITY;
ALTER TABLE field_context_boundary_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_context_boundary_version FORCE ROW LEVEL SECURITY;
CREATE POLICY field_context_tenant_isolation ON field_context
  USING (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true')
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true');
CREATE POLICY field_context_boundary_version_tenant_isolation
  ON field_context_boundary_version
  USING (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true')
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true');
GRANT SELECT, INSERT, UPDATE, DELETE ON field_context, field_context_boundary_version TO ribeira_app;

-- Field registration evidence is accepted only when it points to the same tenant.
CREATE OR REPLACE FUNCTION enforce_evidence_reference_tenant()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  referenced_tenant uuid;
BEGIN
  IF NEW.evidence_type = 'OBSERVATION' THEN
    SELECT tenant_id INTO referenced_tenant FROM observation WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'PROPERTY' THEN
    SELECT tenant_id INTO referenced_tenant FROM property WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'DECISION' THEN
    SELECT tenant_id INTO referenced_tenant FROM decision WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'SATELLITE_SCENE' THEN
    SELECT tenant_id INTO referenced_tenant FROM satellite_scene WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'DERIVED_PRODUCT' THEN
    SELECT tenant_id INTO referenced_tenant FROM derived_product WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'ASSET_REGISTRATION' THEN
    SELECT tenant_id INTO referenced_tenant FROM asset WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'FIELD_REGISTRATION' THEN
    SELECT tenant_id INTO referenced_tenant FROM field_context WHERE id = NEW.reference_id;
  ELSE
    RAISE EXCEPTION 'unsupported evidence reference type: %', NEW.evidence_type
      USING ERRCODE = 'check_violation';
  END IF;
  IF referenced_tenant IS NULL OR referenced_tenant <> NEW.tenant_id THEN
    RAISE EXCEPTION 'evidence reference crosses tenant boundary'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION enforce_evidence_reference_tenant() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION enforce_evidence_reference_tenant() TO ribeira_app;

