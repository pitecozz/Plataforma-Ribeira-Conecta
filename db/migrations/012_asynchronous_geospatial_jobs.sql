-- PostgreSQL is the durable queue for geospatial work. Existing PENDING jobs
-- become QUEUED; no product, evidence, or object is changed by this migration.
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS failure_code text;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS attempt integer NOT NULL DEFAULT 0;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS claimed_by text;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS requested_by text;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE processing_job ADD COLUMN IF NOT EXISTS correlation_id text;

UPDATE processing_job SET status = 'QUEUED' WHERE status = 'PENDING';
ALTER TABLE processing_job DROP CONSTRAINT IF EXISTS processing_job_status_check;
ALTER TABLE processing_job ADD CONSTRAINT processing_job_status_check
  CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'CANCELLED'));
ALTER TABLE processing_job ADD CONSTRAINT processing_job_attempt_check
  CHECK (attempt >= 0 AND max_attempts >= 1 AND attempt <= max_attempts);
CREATE INDEX IF NOT EXISTS processing_job_queue_idx
  ON processing_job (status, next_attempt_at, created_at)
  WHERE status = 'QUEUED';
CREATE INDEX IF NOT EXISTS processing_job_heartbeat_idx
  ON processing_job (heartbeat_at)
  WHERE status = 'RUNNING';

CREATE TABLE IF NOT EXISTS processing_job_transition (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  job_id uuid NOT NULL,
  from_status text,
  to_status text NOT NULL,
  attempt integer NOT NULL,
  actor text NOT NULL,
  worker_id text,
  failure_code text,
  failure_reason text,
  request_id text,
  correlation_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES processing_job(tenant_id, id),
  CHECK (from_status IS NULL OR from_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'CANCELLED')),
  CHECK (to_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'CANCELLED'))
);
ALTER TABLE processing_job_transition ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_job_transition FORCE ROW LEVEL SECURITY;
CREATE POLICY processing_job_transition_tenant_isolation ON processing_job_transition
  USING (tenant_id::text = current_setting('app.tenant_id', true) OR current_setting('app.platform_admin', true) = 'true')
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true) OR current_setting('app.platform_admin', true) = 'true');
GRANT SELECT, INSERT ON TABLE processing_job_transition TO ribeira_app;
