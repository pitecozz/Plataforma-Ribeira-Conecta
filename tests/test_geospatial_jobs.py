from __future__ import annotations

import unittest

from ribeira_platform.geospatial import ProcessingJob, ProcessingJobStatus
from ribeira_platform.geospatial_repository import GeospatialRepository
from ribeira_platform.geospatial_worker import GeospatialJobWorker
from ribeira_platform.models import new_id
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


def queued_job(tenant_id: str, key: str) -> ProcessingJob:
    return ProcessingJob(
        new_id(),
        tenant_id,
        new_id(),
        new_id(),
        "NDVI",
        "NDVI",
        "test",
        {},
        ProcessingJobStatus.QUEUED,
        key,
    )


class GeospatialJobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.app = RibeiraApplication(self.store)
        self.tenant = self.app.create_tenant("Job tenant")
        self.other_tenant = self.app.create_tenant("Other job tenant")
        self.repository = GeospatialRepository(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_enqueue_claim_transition_idempotency_and_cross_tenant_isolation(
        self,
    ) -> None:
        job = queued_job(self.tenant.id, "logical-ndvi-request")
        with self.store.tenant_transaction(self.tenant.id):
            persisted = self.repository.create_job(job, "requester")
            duplicate = self.repository.create_job(
                queued_job(self.tenant.id, "logical-ndvi-request"), "requester"
            )
            claimed = self.repository.claim_next_job("worker-a")
            competing_claim = self.repository.claim_next_job("worker-b")
        self.assertEqual(duplicate.id, persisted.id)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.status, ProcessingJobStatus.RUNNING)
        self.assertEqual(claimed.attempt, 1)
        self.assertIsNone(competing_claim)
        self.assertIsNone(self.repository.get_job(self.other_tenant.id, persisted.id))
        with self.store.tenant_transaction(self.tenant.id):
            completed = self.repository.mark_job(
                self.tenant.id,
                persisted.id,
                ProcessingJobStatus.SUCCEEDED,
                output_product_id=new_id(),
                actor="worker:worker-a",
                worker_id="worker-a",
            )
            transitions = self.repository.list_job_transitions(
                self.tenant.id, persisted.id
            )
        self.assertEqual(completed.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(
            [item.to_status for item in transitions],
            [
                ProcessingJobStatus.QUEUED,
                ProcessingJobStatus.RUNNING,
                ProcessingJobStatus.SUCCEEDED,
            ],
        )
        self.assertEqual(transitions[1].worker_id, "worker-a")

    def test_stale_recovery_and_auditable_retry_preserve_one_job(self) -> None:
        job = queued_job(self.tenant.id, "retry-request")
        with self.store.tenant_transaction(self.tenant.id):
            self.repository.create_job(job, "requester")
            claimed = self.repository.claim_next_job("worker-a")
            assert claimed is not None
            self.repository._execute(
                "UPDATE processing_job SET heartbeat_at=? WHERE id=?",  # nosec B608 - test-only internal table
                ["2000-01-01T00:00:00+00:00", job.id],
            )
            self.assertEqual(
                self.repository.recover_stale_jobs(
                    "2001-01-01T00:00:00+00:00", "worker:recovery"
                ),
                1,
            )
            recovered = self.repository.get_job(self.tenant.id, job.id)
            assert recovered is not None
            self.assertEqual(recovered.status, ProcessingJobStatus.QUEUED)
            claimed_again = self.repository.claim_next_job("worker-b")
            assert claimed_again is not None
            failed = self.repository.mark_job(
                self.tenant.id,
                job.id,
                ProcessingJobStatus.FAILED,
                failure_code="SOURCE_UNAVAILABLE",
                failure_reason="SOURCE_UNAVAILABLE",
                actor="worker:worker-b",
                worker_id="worker-b",
            )
            retried = self.repository.retry_job(self.tenant.id, job.id, "requester")
        self.assertEqual(failed.attempt, 2)
        self.assertEqual(retried.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(self.repository.get_job(self.tenant.id, job.id).id, job.id)  # type: ignore[union-attr]

    def test_worker_failure_is_persisted_without_a_product(self) -> None:
        with self.store.tenant_transaction(self.tenant.id):
            self.repository.create_job(
                queued_job(self.tenant.id, "worker-failure"), "requester"
            )
        result = GeospatialJobWorker(
            self.app, "test-worker", stale_after_seconds=60
        ).process_one()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, ProcessingJobStatus.FAILED)
        self.assertEqual(result.output_product_id, None)
        self.assertEqual(result.failure_code, "LookupError")


if __name__ == "__main__":
    unittest.main()
