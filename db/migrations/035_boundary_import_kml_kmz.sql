-- KML/KMZ are optional, review-only boundary evidence. Their raw bytes and original format remain immutable.
ALTER TABLE boundary_import DROP CONSTRAINT boundary_import_original_format_check, ADD CONSTRAINT boundary_import_original_format_check CHECK (original_format IN ('GEOJSON', 'KML', 'KMZ'));
