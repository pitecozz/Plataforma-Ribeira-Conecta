ALTER TABLE field_context_boundary_version
  ADD CONSTRAINT field_context_boundary_version_snapshot_key
  UNIQUE (tenant_id, field_context_id, version, geometry_checksum);

ALTER TABLE decision
  ADD COLUMN subject_field_boundary_version integer,
  ADD COLUMN subject_field_boundary_checksum text;

UPDATE decision decision_item
   SET subject_field_boundary_version = version.version,
       subject_field_boundary_checksum = version.geometry_checksum
  FROM field_context_boundary_version version
 WHERE decision_item.tenant_id = version.tenant_id
   AND decision_item.subject_field_id = version.field_context_id
   AND version.version = 1;

ALTER TABLE decision
  ADD CONSTRAINT decision_field_boundary_snapshot_check CHECK (
    (subject_field_id IS NULL AND subject_field_boundary_version IS NULL AND subject_field_boundary_checksum IS NULL)
    OR (
      subject_field_id IS NOT NULL
      AND subject_field_boundary_version IS NOT NULL
      AND subject_field_boundary_version > 0
      AND subject_field_boundary_checksum IS NOT NULL
      AND length(subject_field_boundary_checksum) = 64
    )
  ),
  ADD CONSTRAINT decision_subject_field_boundary_fk
    FOREIGN KEY (
      tenant_id,
      subject_field_id,
      subject_field_boundary_version,
      subject_field_boundary_checksum
    ) REFERENCES field_context_boundary_version(
      tenant_id,
      field_context_id,
      version,
      geometry_checksum
    );
