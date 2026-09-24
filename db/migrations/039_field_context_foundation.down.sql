DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM field_context)
     OR EXISTS (SELECT 1 FROM evidence WHERE evidence_type='FIELD_REGISTRATION') THEN
    RAISE EXCEPTION 'cannot rollback 039 after field context or field evidence has been stored';
  END IF;
END $$;

DROP TRIGGER field_context_boundary_property_guard ON field_context_boundary_version;
DROP FUNCTION field_context_boundary_property_guard();
DROP POLICY field_context_boundary_version_tenant_isolation ON field_context_boundary_version;
DROP POLICY field_context_tenant_isolation ON field_context;
DROP TABLE field_context_boundary_version;
DROP TABLE field_context;

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
  ELSIF NEW.evidence_type = 'SATELLITE_SCENE' THEN
    SELECT tenant_id INTO referenced_tenant FROM satellite_scene WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'DERIVED_PRODUCT' THEN
    SELECT tenant_id INTO referenced_tenant FROM derived_product WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'ASSET_REGISTRATION' THEN
    SELECT tenant_id INTO referenced_tenant FROM asset WHERE id = NEW.reference_id;
  ELSE
    RAISE EXCEPTION 'unsupported evidence reference type: %', NEW.evidence_type
      USING ERRCODE = 'check_violation';
  END IF;
  IF referenced_tenant IS NULL OR referenced_tenant <> NEW.tenant_id THEN
    RAISE EXCEPTION 'evidence reference crosses tenant boundary'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION enforce_evidence_reference_tenant() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION enforce_evidence_reference_tenant() TO ribeira_app;
