ALTER TABLE field_context_boundary_version
  ADD CONSTRAINT field_context_boundary_version_property_snapshot_key
  UNIQUE (tenant_id, property_id, field_context_id, version, geometry_checksum);

ALTER TABLE processing_job
  ADD COLUMN field_id uuid,
  ADD COLUMN field_boundary_version integer,
  ADD COLUMN field_boundary_checksum text,
  ADD CONSTRAINT processing_job_field_snapshot_check CHECK (
    (field_id IS NULL AND field_boundary_version IS NULL AND field_boundary_checksum IS NULL)
    OR (
      job_type = 'TEMPORAL_DELTA'
      AND field_id IS NOT NULL
      AND field_boundary_version IS NOT NULL
      AND field_boundary_version > 0
      AND field_boundary_checksum IS NOT NULL
      AND length(field_boundary_checksum) = 64
    )
  ),
  ADD CONSTRAINT processing_job_field_snapshot_fk
    FOREIGN KEY (tenant_id, property_id, field_id, field_boundary_version, field_boundary_checksum)
    REFERENCES field_context_boundary_version(
      tenant_id, property_id, field_context_id, version, geometry_checksum
    ),
  ADD CONSTRAINT processing_job_field_snapshot_identity
    UNIQUE (tenant_id, id, property_id, field_id, field_boundary_version, field_boundary_checksum);

ALTER TABLE derived_product
  ADD COLUMN field_id uuid,
  ADD COLUMN field_boundary_version integer,
  ADD COLUMN field_boundary_checksum text,
  ADD CONSTRAINT derived_product_field_snapshot_check CHECK (
    (field_id IS NULL AND field_boundary_version IS NULL AND field_boundary_checksum IS NULL)
    OR (
      product_type = 'NDVI_DELTA'
      AND field_id IS NOT NULL
      AND field_boundary_version IS NOT NULL
      AND field_boundary_version > 0
      AND field_boundary_checksum IS NOT NULL
      AND length(field_boundary_checksum) = 64
    )
  ),
  ADD CONSTRAINT derived_product_field_snapshot_fk
    FOREIGN KEY (tenant_id, property_id, field_id, field_boundary_version, field_boundary_checksum)
    REFERENCES field_context_boundary_version(
      tenant_id, property_id, field_context_id, version, geometry_checksum
    ),
  ADD CONSTRAINT derived_product_job_field_snapshot_fk
    FOREIGN KEY (
      tenant_id, processing_job_id, property_id, field_id,
      field_boundary_version, field_boundary_checksum
    ) REFERENCES processing_job(
      tenant_id, id, property_id, field_id,
      field_boundary_version, field_boundary_checksum
    );

CREATE OR REPLACE FUNCTION field_delta_snapshot_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF ROW(OLD.field_id, OLD.field_boundary_version, OLD.field_boundary_checksum)
     IS DISTINCT FROM
     ROW(NEW.field_id, NEW.field_boundary_version, NEW.field_boundary_checksum) THEN
    RAISE EXCEPTION 'field delta boundary snapshot is immutable'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION field_delta_snapshot_immutable() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION field_delta_snapshot_immutable() TO ribeira_app;
CREATE TRIGGER processing_job_field_delta_snapshot_immutable
  BEFORE UPDATE ON processing_job
  FOR EACH ROW EXECUTE FUNCTION field_delta_snapshot_immutable();
CREATE TRIGGER derived_product_field_delta_snapshot_immutable
  BEFORE UPDATE ON derived_product
  FOR EACH ROW EXECUTE FUNCTION field_delta_snapshot_immutable();
