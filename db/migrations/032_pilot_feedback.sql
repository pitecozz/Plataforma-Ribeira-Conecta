-- Tenant-isolated pilot product feedback. It is an auditable product input,
-- never a substitute for property, environmental, agronomic or commercial evidence.
CREATE TABLE pilot_feedback (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid REFERENCES property(id),
  submitted_by text NOT NULL,
  feedback_type text NOT NULL CHECK (feedback_type IN (
    'BUG', 'CONFUSING', 'INCORRECT_DATA', 'MISSING_FEATURE', 'SUGGESTION', 'USEFUL'
  )),
  page text NOT NULL CHECK (char_length(page) BETWEEN 1 AND 120),
  feature_id text NOT NULL CHECK (char_length(feature_id) BETWEEN 1 AND 120),
  message text NOT NULL CHECK (char_length(message) BETWEEN 1 AND 4000),
  created_at timestamptz NOT NULL
);
CREATE INDEX pilot_feedback_tenant_created_idx ON pilot_feedback(tenant_id, created_at DESC);

CREATE OR REPLACE FUNCTION enforce_pilot_feedback_property_tenant()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.property_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM property WHERE id=NEW.property_id AND tenant_id=NEW.tenant_id
  ) THEN
    RAISE EXCEPTION 'pilot feedback property must belong to feedback tenant';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pilot_feedback_property_tenant_trigger
  BEFORE INSERT OR UPDATE OF tenant_id,property_id ON pilot_feedback
  FOR EACH ROW EXECUTE FUNCTION enforce_pilot_feedback_property_tenant();

ALTER TABLE pilot_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_feedback FORCE ROW LEVEL SECURITY;
CREATE POLICY pilot_feedback_tenant_isolation ON pilot_feedback
  USING (
    tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true'
  )
  WITH CHECK (
    tenant_id::text = current_setting('app.tenant_id', true)
    OR current_setting('app.platform_admin', true) = 'true'
  );
GRANT SELECT, INSERT ON pilot_feedback TO ribeira_app;
