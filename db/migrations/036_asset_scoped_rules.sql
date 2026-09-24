-- An asset-scoped rule is explicit, tenant-bound context; it never applies during
-- a property-only evaluation and it cannot point across tenants.
ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_check;
ALTER TABLE rule_definition
  ADD COLUMN scope_asset_id uuid,
  ADD CONSTRAINT rule_definition_scope_asset_tenant_fk
    FOREIGN KEY (tenant_id, scope_asset_id) REFERENCES asset(tenant_id, id),
  ADD CONSTRAINT rule_definition_scope_check CHECK (
    (scope_type='TENANT' AND scope_property_id IS NULL AND scope_asset_id IS NULL)
    OR (scope_type='PROPERTY' AND scope_property_id IS NOT NULL AND scope_asset_id IS NULL)
    OR (scope_type='ASSET' AND scope_property_id IS NULL AND scope_asset_id IS NOT NULL)
  );
DROP INDEX rule_definition_scope_idx;
CREATE INDEX rule_definition_scope_idx
  ON rule_definition(
    tenant_id,metric,status,scope_type,scope_property_id,scope_asset_id,version DESC
  );

-- A decision remains property-bound because observations are property-scoped.
-- subject_asset_id records only the declared asset context used to select a rule.
ALTER TABLE decision
  ADD COLUMN subject_asset_id uuid,
  ADD CONSTRAINT decision_subject_asset_tenant_fk
    FOREIGN KEY (tenant_id, subject_asset_id) REFERENCES asset(tenant_id, id);

CREATE OR REPLACE FUNCTION decision_subject_asset_property_check()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.subject_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
      FROM asset
     WHERE id=NEW.subject_asset_id
       AND tenant_id=NEW.tenant_id
       AND property_id=NEW.property_id
  ) THEN
    RAISE EXCEPTION 'decision subject asset must belong to the decision property in the tenant'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION decision_subject_asset_property_check() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION decision_subject_asset_property_check() TO ribeira_app;
CREATE TRIGGER decision_subject_asset_property_guard
  BEFORE INSERT OR UPDATE ON decision
  FOR EACH ROW EXECUTE FUNCTION decision_subject_asset_property_check();

-- Asset registration is tenant-local provenance.  It is admissible as rule
-- applicability context, never as an observed measurement.
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
    RAISE EXCEPTION 'unsupported evidence reference type: %', NEW.evidence_type USING ERRCODE = 'check_violation';
  END IF;
  IF referenced_tenant IS NULL OR referenced_tenant <> NEW.tenant_id THEN
    RAISE EXCEPTION 'evidence reference crosses tenant boundary' USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
