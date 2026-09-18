-- Job history is audit evidence. Refuse rollback while it would discard it.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM processing_job_transition) THEN
    RAISE EXCEPTION 'cannot rollback asynchronous jobs while transition evidence exists';
  END IF;
  IF EXISTS (SELECT 1 FROM processing_job WHERE status = 'BLOCKED') THEN
    RAISE EXCEPTION 'cannot rollback asynchronous jobs while BLOCKED jobs exist';
  END IF;
END $$;

DROP POLICY IF EXISTS processing_job_transition_tenant_isolation ON processing_job_transition;
DROP TABLE IF EXISTS processing_job_transition;
ALTER TABLE processing_job DROP CONSTRAINT IF EXISTS processing_job_attempt_check;
ALTER TABLE processing_job DROP CONSTRAINT IF EXISTS processing_job_status_check;
UPDATE processing_job SET status = 'PENDING' WHERE status = 'QUEUED';
ALTER TABLE processing_job ADD CONSTRAINT processing_job_status_check
  CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'));
DROP INDEX IF EXISTS processing_job_queue_idx, processing_job_heartbeat_idx;
ALTER TABLE processing_job DROP COLUMN IF EXISTS correlation_id;
ALTER TABLE processing_job DROP COLUMN IF EXISTS request_id;
ALTER TABLE processing_job DROP COLUMN IF EXISTS requested_by;
ALTER TABLE processing_job DROP COLUMN IF EXISTS claimed_at;
ALTER TABLE processing_job DROP COLUMN IF EXISTS claimed_by;
ALTER TABLE processing_job DROP COLUMN IF EXISTS heartbeat_at;
ALTER TABLE processing_job DROP COLUMN IF EXISTS next_attempt_at;
ALTER TABLE processing_job DROP COLUMN IF EXISTS max_attempts;
ALTER TABLE processing_job DROP COLUMN IF EXISTS attempt;
ALTER TABLE processing_job DROP COLUMN IF EXISTS failure_code;
