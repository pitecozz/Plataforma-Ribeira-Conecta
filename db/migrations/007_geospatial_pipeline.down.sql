ALTER TABLE processing_job DROP CONSTRAINT IF EXISTS processing_job_output_product_fk;
DROP TABLE IF EXISTS derived_product;
DROP TABLE IF EXISTS processing_job;
DROP TABLE IF EXISTS satellite_search_candidate;
DROP TABLE IF EXISTS satellite_asset;
ALTER TABLE satellite_search DROP CONSTRAINT IF EXISTS satellite_search_selected_scene_fk;
DROP TABLE IF EXISTS satellite_scene;
DROP TABLE IF EXISTS satellite_search;
DROP TABLE IF EXISTS geospatial_collection;

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
  ELSE
    RAISE EXCEPTION 'unsupported evidence reference type: %', NEW.evidence_type USING ERRCODE = 'check_violation';
  END IF;
  IF referenced_tenant IS NULL OR referenced_tenant <> NEW.tenant_id THEN
    RAISE EXCEPTION 'evidence reference crosses tenant boundary' USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;

ALTER TABLE provider_registry DROP COLUMN IF EXISTS stac_version;
ALTER TABLE provider_registry DROP COLUMN IF EXISTS api_standard;
ALTER TABLE provider_registry DROP COLUMN IF EXISTS catalog_endpoint;
ALTER TABLE provider_registry DROP COLUMN IF EXISTS documentation_url;
ALTER TABLE provider_registry DROP COLUMN IF EXISTS provider_type;
ALTER TABLE provider_registry DROP COLUMN IF EXISTS organization;
