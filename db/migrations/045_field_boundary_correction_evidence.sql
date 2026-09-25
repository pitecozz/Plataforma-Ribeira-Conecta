CREATE UNIQUE INDEX field_context_boundary_version_tenant_id_uq
  ON field_context_boundary_version(tenant_id, id);

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
  ELSIF NEW.evidence_type = 'FIELD_REGISTRATION' THEN
    SELECT tenant_id INTO referenced_tenant FROM field_context WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'FIELD_BOUNDARY_CORRECTION' THEN
    SELECT tenant_id INTO referenced_tenant FROM field_context_boundary_version WHERE id = NEW.reference_id;
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
