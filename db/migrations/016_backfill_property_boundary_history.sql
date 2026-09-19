-- Preserve the current, pre-015 boundary as explicit history.  This does not
-- alter geometry or product/provenance records; UNKNOWN remains explicit where
-- the historical boundary source was absent.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE property
SET boundary_checksum = encode(digest(ST_AsGeoJSON(geometry)::bytea, 'sha256'), 'hex')
WHERE geometry IS NOT NULL AND boundary_checksum IS NULL;

INSERT INTO property_boundary_version (
  id, tenant_id, property_id, version, geometry, geometry_crs,
  boundary_source, data_classification, checksum, reason, actor,
  effective_at, created_at
)
SELECT
  gen_random_uuid(), p.tenant_id, p.id, 1, p.geometry,
  COALESCE(NULLIF(p.geometry_crs, ''), 'EPSG:4326'),
  COALESCE(NULLIF(p.boundary_source, ''), 'UNKNOWN'),
  p.data_classification, p.boundary_checksum,
  'BACKFILLED_CURRENT_BOUNDARY_STATE', 'migration-016',
  COALESCE(p.updated_at, p.created_at), now()
FROM property p
WHERE p.geometry IS NOT NULL
  AND p.boundary_checksum IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM property_boundary_version v
    WHERE v.tenant_id = p.tenant_id AND v.property_id = p.id
  );
