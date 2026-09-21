DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM municipality_reference) OR EXISTS (SELECT 1 FROM banana_municipal_baseline) OR EXISTS (SELECT 1 FROM spatial_scope_municipality) THEN
  RAISE EXCEPTION 'cannot rollback 020 after spatial or baseline data has been stored';
 END IF;
END $$;
DROP TABLE spatial_scope_municipality;
DROP TABLE banana_municipal_baseline;
DROP TABLE spatial_scope_definition;
DROP TABLE municipality_reference;
ALTER TABLE geographic_scope DROP COLUMN metadata, DROP COLUMN valid_from, DROP COLUMN source_version, DROP COLUMN source, DROP COLUMN scope_type;
