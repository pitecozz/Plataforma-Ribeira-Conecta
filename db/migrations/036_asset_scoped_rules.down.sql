DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM decision WHERE subject_asset_id IS NOT NULL)
     OR EXISTS (SELECT 1 FROM rule_definition WHERE scope_type='ASSET') THEN
    RAISE EXCEPTION 'cannot rollback 036 after asset-scoped rules or decisions have been stored';
  END IF;
  IF EXISTS (SELECT 1 FROM evidence WHERE evidence_type='ASSET_REGISTRATION') THEN
    RAISE EXCEPTION 'cannot rollback 036 after asset registration evidence has been stored';
  END IF;
END $$;

DROP TRIGGER decision_subject_asset_property_guard ON decision;
DROP FUNCTION decision_subject_asset_property_check();
ALTER TABLE decision DROP CONSTRAINT decision_subject_asset_tenant_fk;
ALTER TABLE decision DROP COLUMN subject_asset_id;

ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_check;
ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_asset_tenant_fk;
DROP INDEX rule_definition_scope_idx;
ALTER TABLE rule_definition DROP COLUMN scope_asset_id;
ALTER TABLE rule_definition ADD CONSTRAINT rule_definition_scope_check CHECK (
  (scope_type='TENANT' AND scope_property_id IS NULL)
  OR (scope_type='PROPERTY' AND scope_property_id IS NOT NULL)
);
CREATE INDEX rule_definition_scope_idx
  ON rule_definition(tenant_id,metric,status,scope_type,scope_property_id,version DESC);

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
  ELSE
    RAISE EXCEPTION 'unsupported evidence reference type: %', NEW.evidence_type USING ERRCODE = 'check_violation';
  END IF;
  IF referenced_tenant IS NULL OR referenced_tenant <> NEW.tenant_id THEN
    RAISE EXCEPTION 'evidence reference crosses tenant boundary' USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
