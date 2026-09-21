DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pilot_feedback) THEN
    RAISE EXCEPTION 'cannot rollback 032 after pilot feedback has been stored';
  END IF;
END $$;
DROP TRIGGER pilot_feedback_property_tenant_trigger ON pilot_feedback;
DROP FUNCTION enforce_pilot_feedback_property_tenant();
DROP TABLE pilot_feedback;
