-- 012 introduced worker leases. Jobs already marked RUNNING by the former
-- synchronous path had no heartbeat and could never become stale candidates.
-- They are old persisted work, not new requests; make their recovery explicit.
UPDATE processing_job
SET heartbeat_at = COALESCE(started_at, created_at),
    claimed_at = COALESCE(claimed_at, started_at, created_at),
    claimed_by = COALESCE(claimed_by, 'legacy-pre-012')
WHERE status = 'RUNNING' AND heartbeat_at IS NULL;
