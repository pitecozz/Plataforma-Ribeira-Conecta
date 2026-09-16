-- Cross-tenant integrity: UUID equality alone is not an authorization boundary.
-- All tenant-owned references below must match both tenant_id and resource id.

ALTER TABLE property ADD CONSTRAINT property_tenant_id_uq UNIQUE (tenant_id, id);
ALTER TABLE source ADD CONSTRAINT source_tenant_id_uq UNIQUE (tenant_id, id);
ALTER TABLE decision ADD CONSTRAINT decision_tenant_id_uq UNIQUE (tenant_id, id);

ALTER TABLE observation DROP CONSTRAINT IF EXISTS observation_property_id_fkey;
ALTER TABLE observation DROP CONSTRAINT IF EXISTS observation_source_id_fkey;
ALTER TABLE observation ADD CONSTRAINT observation_property_tenant_fk FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id);
ALTER TABLE observation ADD CONSTRAINT observation_source_tenant_fk FOREIGN KEY (tenant_id, source_id) REFERENCES source(tenant_id, id);

ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_source_id_fkey;
ALTER TABLE evidence ADD CONSTRAINT evidence_source_tenant_fk FOREIGN KEY (tenant_id, source_id) REFERENCES source(tenant_id, id);

ALTER TABLE decision DROP CONSTRAINT IF EXISTS decision_property_id_fkey;
ALTER TABLE decision ADD CONSTRAINT decision_property_tenant_fk FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id);

ALTER TABLE alert DROP CONSTRAINT IF EXISTS alert_property_id_fkey;
ALTER TABLE alert DROP CONSTRAINT IF EXISTS alert_decision_id_fkey;
ALTER TABLE alert ADD CONSTRAINT alert_property_tenant_fk FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id);
ALTER TABLE alert ADD CONSTRAINT alert_decision_tenant_fk FOREIGN KEY (tenant_id, decision_id) REFERENCES decision(tenant_id, id);

ALTER TABLE action DROP CONSTRAINT IF EXISTS action_decision_id_fkey;
ALTER TABLE action ADD CONSTRAINT action_decision_tenant_fk FOREIGN KEY (tenant_id, decision_id) REFERENCES decision(tenant_id, id);

ALTER TABLE data_quality_event DROP CONSTRAINT IF EXISTS data_quality_event_property_id_fkey;
ALTER TABLE data_quality_event DROP CONSTRAINT IF EXISTS data_quality_event_source_id_fkey;
ALTER TABLE data_quality_event ADD CONSTRAINT quality_property_tenant_fk FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id);
ALTER TABLE data_quality_event ADD CONSTRAINT quality_source_tenant_fk FOREIGN KEY (tenant_id, source_id) REFERENCES source(tenant_id, id);

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

REVOKE ALL ON FUNCTION enforce_evidence_reference_tenant() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION enforce_evidence_reference_tenant() TO ribeira_app;
DROP TRIGGER IF EXISTS evidence_reference_tenant_guard ON evidence;
CREATE TRIGGER evidence_reference_tenant_guard
  BEFORE INSERT OR UPDATE ON evidence
  FOR EACH ROW EXECUTE FUNCTION enforce_evidence_reference_tenant();
