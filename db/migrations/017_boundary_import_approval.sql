-- Auditable, tenant-scoped GeoJSON boundary imports. Imports never change a
-- property until an authorized reviewer approves them.
CREATE TABLE boundary_import (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  original_filename text NOT NULL,
  original_format text NOT NULL CHECK (original_format = 'GEOJSON'),
  file_size_bytes bigint NOT NULL CHECK (file_size_bytes >= 0),
  file_sha256 text NOT NULL CHECK (length(file_sha256) = 64),
  object_reference text NOT NULL,
  original_crs text,
  detected_crs text,
  target_crs text,
  geometry geometry(Geometry, 4326),
  geometry_checksum text,
  boundary_source text NOT NULL,
  data_classification text NOT NULL,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK (status IN ('UPLOADED','PARSED','VALIDATED','NEEDS_REVIEW','APPROVED','REJECTED','FAILED')),
  created_by text NOT NULL,
  reviewed_by text,
  review_reason text,
  expected_property_checksum text,
  approved_boundary_version integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (tenant_id, property_id, approved_boundary_version)
    REFERENCES property_boundary_version(tenant_id, property_id, version),
  CHECK (geometry_checksum IS NULL OR length(geometry_checksum) = 64),
  CHECK (status <> 'APPROVED' OR (
    reviewed_by IS NOT NULL AND review_reason IS NOT NULL AND reviewed_at IS NOT NULL
    AND approved_boundary_version IS NOT NULL
  )),
  CHECK (status NOT IN ('REJECTED') OR (
    reviewed_by IS NOT NULL AND review_reason IS NOT NULL AND reviewed_at IS NOT NULL
  ))
);
CREATE FUNCTION boundary_import_transition_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status NOT IN ('NEEDS_REVIEW', 'FAILED')
       OR NEW.reviewed_by IS NOT NULL OR NEW.review_reason IS NOT NULL
       OR NEW.reviewed_at IS NOT NULL OR NEW.approved_boundary_version IS NOT NULL THEN
      RAISE EXCEPTION 'boundary import must be created as NEEDS_REVIEW or FAILED';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'NEEDS_REVIEW' OR NEW.status NOT IN ('APPROVED', 'REJECTED') THEN
    RAISE EXCEPTION 'invalid boundary import state transition';
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.property_id IS DISTINCT FROM OLD.property_id
     OR NEW.file_sha256 IS DISTINCT FROM OLD.file_sha256
     OR NEW.object_reference IS DISTINCT FROM OLD.object_reference
     OR NEW.geometry_checksum IS DISTINCT FROM OLD.geometry_checksum
     OR NEW.geometry IS DISTINCT FROM OLD.geometry
     OR NEW.expected_property_checksum IS DISTINCT FROM OLD.expected_property_checksum
     OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'boundary import evidence is immutable';
  END IF;
  IF NEW.status = 'REJECTED' AND NEW.approved_boundary_version IS NOT NULL THEN
    RAISE EXCEPTION 'rejected boundary import cannot have an approved version';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER boundary_import_transition_guard
  BEFORE INSERT OR UPDATE ON boundary_import
  FOR EACH ROW EXECUTE FUNCTION boundary_import_transition_guard();
CREATE INDEX boundary_import_tenant_property_status_idx
  ON boundary_import (tenant_id, property_id, status, created_at DESC);
CREATE INDEX boundary_import_tenant_created_idx
  ON boundary_import (tenant_id, created_at DESC);

ALTER TABLE boundary_import ENABLE ROW LEVEL SECURITY;
ALTER TABLE boundary_import FORCE ROW LEVEL SECURITY;
CREATE POLICY boundary_import_tenant_isolation ON boundary_import
  USING (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true')
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true');
GRANT SELECT, INSERT, UPDATE, DELETE ON boundary_import TO ribeira_app;
