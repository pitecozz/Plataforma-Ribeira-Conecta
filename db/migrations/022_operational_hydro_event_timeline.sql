-- Phase 1P.4: operational reconciliation evidence and factual event timeline.
CREATE TABLE hydro_ingestion_run (
  id uuid PRIMARY KEY,
  provider text NOT NULL,
  delivery_channel text NOT NULL,
  ingestion_context text NOT NULL CHECK (ingestion_context IN ('OPERATIONAL_RECONCILIATION','HISTORICAL_BACKFILL')),
  started_at timestamptz NOT NULL,
  finished_at timestamptz NOT NULL,
  status text NOT NULL CHECK (status IN ('SUCCESS','DEGRADED','SOURCE_UNAVAILABLE')),
  observations_received integer NOT NULL DEFAULT 0 CHECK (observations_received >= 0),
  observations_inserted integer NOT NULL DEFAULT 0 CHECK (observations_inserted >= 0),
  duplicates_ignored integer NOT NULL DEFAULT 0 CHECK (duplicates_ignored >= 0),
  invalid_observations integer NOT NULL DEFAULT 0 CHECK (invalid_observations >= 0),
  provider_errors integer NOT NULL DEFAULT 0 CHECK (provider_errors >= 0),
  duration_seconds numeric NOT NULL CHECK (duration_seconds >= 0),
  max_report_lag_seconds numeric,
  detail_sanitized text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE operational_event (
  id uuid PRIMARY KEY,
  event_key text NOT NULL UNIQUE,
  title text NOT NULL,
  start_at timestamptz NOT NULL,
  end_at timestamptz,
  status text NOT NULL CHECK (status IN ('OPEN','HISTORICAL','UNKNOWN')),
  classification text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE operational_event_evidence (
  event_id uuid NOT NULL REFERENCES operational_event(id),
  source_table text NOT NULL,
  source_record_id uuid NOT NULL,
  evidence_type text NOT NULL,
  classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(event_id,source_table,source_record_id,evidence_type)
);

CREATE TABLE operational_event_timeline_entry (
  id uuid PRIMARY KEY,
  event_id uuid NOT NULL REFERENCES operational_event(id),
  event_type text NOT NULL CHECK (event_type IN ('RAINFALL_OBSERVATION','RAINFALL_ACCUMULATION_PEAK','RESERVOIR_OPERATION','CLIMATE_CONTEXT')),
  occurred_at timestamptz NOT NULL,
  classification text NOT NULL,
  source_table text NOT NULL,
  source_record_id uuid,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id,event_type,source_table,source_record_id)
);

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('hydro_ingestion_run','hydro_ingestion_run_global_access'),
    ('operational_event','operational_event_global_access'),
    ('operational_event_evidence','operational_event_evidence_global_access'),
    ('operational_event_timeline_entry','operational_event_timeline_entry_global_access')
  ) AS valueset(table_name,policy_name)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO ribeira_app USING (true) WITH CHECK (true)',item.policy_name,item.table_name);
  END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE,DELETE ON hydro_ingestion_run,operational_event,operational_event_evidence,operational_event_timeline_entry TO ribeira_app;
