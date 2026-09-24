DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM boundary_import WHERE original_format IN ('KML', 'KMZ')) THEN RAISE EXCEPTION 'cannot rollback KML/KMZ import support while immutable import evidence exists'; END IF;
END $$;
ALTER TABLE boundary_import DROP CONSTRAINT boundary_import_original_format_check, ADD CONSTRAINT boundary_import_original_format_check CHECK (original_format = 'GEOJSON');
