-- Development-only bootstrap. Production credentials come from a secret manager.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ribeira_app') THEN
    CREATE ROLE ribeira_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      PASSWORD 'ribeira_app_dev_only';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE ribeira_dev TO ribeira_app;
GRANT USAGE ON SCHEMA public TO ribeira_app;
