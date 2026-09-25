DROP TRIGGER IF EXISTS derived_product_field_delta_snapshot_immutable ON derived_product;
DROP TRIGGER IF EXISTS processing_job_field_delta_snapshot_immutable ON processing_job;
DROP FUNCTION IF EXISTS field_delta_snapshot_immutable();

ALTER TABLE derived_product
  DROP CONSTRAINT derived_product_job_field_snapshot_fk,
  DROP CONSTRAINT derived_product_field_snapshot_fk,
  DROP CONSTRAINT derived_product_field_snapshot_check,
  DROP COLUMN field_boundary_checksum,
  DROP COLUMN field_boundary_version,
  DROP COLUMN field_id;

ALTER TABLE processing_job
  DROP CONSTRAINT processing_job_field_snapshot_identity,
  DROP CONSTRAINT processing_job_field_snapshot_fk,
  DROP CONSTRAINT processing_job_field_snapshot_check,
  DROP COLUMN field_boundary_checksum,
  DROP COLUMN field_boundary_version,
  DROP COLUMN field_id;

ALTER TABLE field_context_boundary_version
  DROP CONSTRAINT field_context_boundary_version_property_snapshot_key;
