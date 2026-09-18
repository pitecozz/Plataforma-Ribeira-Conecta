-- Safe only before a legacy lease has been recovered or claimed by a worker.
UPDATE processing_job
SET heartbeat_at = NULL,
    claimed_at = NULL,
    claimed_by = NULL
WHERE status = 'RUNNING' AND claimed_by = 'legacy-pre-012';
