-- Durable per-property provider refresh.  Boundary geometry is never written by this pipeline.
CREATE TABLE property_refresh_policy (
  tenant_id uuid NOT NULL REFERENCES tenant(id), property_id uuid NOT NULL,
  provider_id text NOT NULL, collection_id text NOT NULL, enabled boolean NOT NULL DEFAULT true,
  frequency_seconds integer NOT NULL CHECK (frequency_seconds BETWEEN 300 AND 604800),
  search_window_days integer NOT NULL CHECK (search_window_days BETWEEN 1 AND 366),
  cloud_cover_limit numeric(5,2), auto_process boolean NOT NULL DEFAULT true,
  last_search_at timestamptz, next_search_at timestamptz, last_success_at timestamptz,
  last_failure_at timestamptz, latest_available_scene_id uuid, latest_usable_scene_id uuid,
  latest_processed_scene_id uuid, retry_count integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','RETRYABLE','BLOCKED','FAILED')),
  failure_code text, failure_reason text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, property_id, provider_id, collection_id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id,id),
  FOREIGN KEY (tenant_id, latest_available_scene_id) REFERENCES satellite_scene(tenant_id,id),
  FOREIGN KEY (tenant_id, latest_usable_scene_id) REFERENCES satellite_scene(tenant_id,id),
  FOREIGN KEY (tenant_id, latest_processed_scene_id) REFERENCES satellite_scene(tenant_id,id)
);
CREATE TABLE property_refresh_run (
  id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenant(id), property_id uuid NOT NULL,
  provider_id text NOT NULL, collection_id text NOT NULL, trigger_type text NOT NULL CHECK (trigger_type IN ('INITIAL_PROPERTY_CONTEXT_REFRESH','SCHEDULED','MANUAL')),
  status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','RETRYABLE','BLOCKED','FAILED')),
  idempotency_key text NOT NULL, scheduled_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz,
  next_attempt_at timestamptz, attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0), max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
  search_id uuid, processing_job_id uuid, failure_code text, failure_reason text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  UNIQUE(tenant_id,idempotency_key), UNIQUE(tenant_id,id),
  FOREIGN KEY (tenant_id,property_id) REFERENCES property(tenant_id,id),
  FOREIGN KEY (tenant_id,search_id) REFERENCES satellite_search(tenant_id,id),
  FOREIGN KEY (tenant_id,processing_job_id) REFERENCES processing_job(tenant_id,id)
);
CREATE INDEX property_refresh_run_due_idx ON property_refresh_run(status,next_attempt_at,scheduled_at) WHERE status IN ('QUEUED','RETRYABLE');
ALTER TABLE property_refresh_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_refresh_policy FORCE ROW LEVEL SECURITY;
ALTER TABLE property_refresh_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_refresh_run FORCE ROW LEVEL SECURITY;
CREATE POLICY property_refresh_policy_tenant_isolation ON property_refresh_policy USING (tenant_id::text=current_setting('app.tenant_id',true) OR current_setting('app.platform_admin',true)='true') WITH CHECK (tenant_id::text=current_setting('app.tenant_id',true) OR current_setting('app.platform_admin',true)='true');
CREATE POLICY property_refresh_run_tenant_isolation ON property_refresh_run USING (tenant_id::text=current_setting('app.tenant_id',true) OR current_setting('app.platform_admin',true)='true') WITH CHECK (tenant_id::text=current_setting('app.tenant_id',true) OR current_setting('app.platform_admin',true)='true');
GRANT SELECT,INSERT,UPDATE ON property_refresh_policy,property_refresh_run TO ribeira_app;
