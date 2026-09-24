DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM property_refresh_run) THEN
    RAISE EXCEPTION 'cannot rollback property automatic refresh while durable run evidence exists';
  END IF;
END $$;
DROP TABLE property_refresh_run;
DROP TABLE property_refresh_policy;
