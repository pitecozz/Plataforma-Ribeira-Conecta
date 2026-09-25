ALTER TABLE decision
  DROP CONSTRAINT decision_subject_field_boundary_fk,
  DROP CONSTRAINT decision_field_boundary_snapshot_check,
  DROP COLUMN subject_field_boundary_checksum,
  DROP COLUMN subject_field_boundary_version;
ALTER TABLE field_context_boundary_version
  DROP CONSTRAINT field_context_boundary_version_snapshot_key;
