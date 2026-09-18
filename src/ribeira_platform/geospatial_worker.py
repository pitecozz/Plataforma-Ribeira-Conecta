"""Private PostgreSQL-backed worker for persisted geospatial jobs."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import signal
import threading
from datetime import UTC, datetime, timedelta
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from .api import Settings, _build_store
from .geospatial import ProcessingJob, ProcessingJobStatus
from .geospatial_repository import GeospatialRepository
from .logging_config import configure_structured_logging
from .postgres import PostgresStore
from .service import RibeiraApplication


LOGGER = logging.getLogger(__name__)
JOB_OUTCOMES = Counter(
    "ribeira_geospatial_jobs_total", "Geospatial job terminal outcomes", ["status"]
)
JOB_DURATION = Histogram(
    "ribeira_geospatial_job_duration_seconds",
    "Geospatial job processing duration",
    ["job_type"],
)
JOB_RETRIES = Counter(
    "ribeira_geospatial_job_retries_total", "Geospatial jobs explicitly retried"
)
STALE_JOBS = Counter(
    "ribeira_geospatial_stale_jobs_total", "Recovered stale geospatial jobs"
)
QUEUED_JOBS = Gauge("ribeira_geospatial_queued_jobs", "Queued geospatial jobs")
RUNNING_JOBS = Gauge("ribeira_geospatial_running_jobs", "Running geospatial jobs")


class GeospatialJobWorker:
    def __init__(
        self,
        application: RibeiraApplication,
        worker_id: str,
        stale_after_seconds: int = 3600,
    ) -> None:
        self.application = application
        self.worker_id = worker_id
        self.stale_after_seconds = stale_after_seconds

    @property
    def repository(self):
        return self.application.geospatial.repository

    def _refresh_metrics(self) -> None:
        with self.application.store.tenant_transaction(None, True):
            counts = self.repository.job_counts()
        QUEUED_JOBS.set(counts.get(ProcessingJobStatus.QUEUED.value, 0))
        RUNNING_JOBS.set(counts.get(ProcessingJobStatus.RUNNING.value, 0))

    def recover_stale_jobs(self) -> int:
        cutoff = (
            datetime.now(UTC) - timedelta(seconds=self.stale_after_seconds)
        ).isoformat()
        with self.application.store.tenant_transaction(None, True):
            recovered = self.repository.recover_stale_jobs(
                cutoff, actor=f"worker:{self.worker_id}"
            )
        if recovered:
            STALE_JOBS.inc(recovered)
            LOGGER.warning(
                "recovered stale geospatial jobs", extra={"count": recovered}
            )
        return recovered

    def _claim(self) -> ProcessingJob | None:
        with self.application.store.tenant_transaction(None, True):
            return self.repository.claim_next_job(self.worker_id)

    def _heartbeat_loop(self, job: ProcessingJob, stop: threading.Event) -> None:
        """Keep a leased PostgreSQL job alive without sharing its connection.

        Rasterio/GDAL work can take longer than an HTTP request. A separate
        private connection prevents a long processing transaction from hiding
        the heartbeat. SQLite is only a test adapter and deliberately has no
        cross-thread connection activity.
        """
        store = self.application.store
        dsn = getattr(store, "dsn", None)
        if not isinstance(store, PostgresStore) or not dsn:
            return
        interval = max(10, min(30, self.stale_after_seconds // 3))
        while not stop.wait(interval):
            heartbeat_store = PostgresStore(dsn)
            try:
                repository = GeospatialRepository(heartbeat_store)
                with heartbeat_store.tenant_transaction(job.tenant_id, True):
                    if not repository.heartbeat(job.tenant_id, job.id, self.worker_id):
                        LOGGER.warning(
                            "geospatial job heartbeat lease was lost",
                            extra={"job_id": job.id, "tenant_id": job.tenant_id},
                        )
                        return
            except Exception:
                LOGGER.exception(
                    "geospatial job heartbeat failed",
                    extra={"job_id": job.id, "tenant_id": job.tenant_id},
                )
            finally:
                heartbeat_store.close()

    def process_one(self) -> ProcessingJob | None:
        self.recover_stale_jobs()
        job = self._claim()
        self._refresh_metrics()
        if job is None:
            return None
        if job.attempt > 1:
            JOB_RETRIES.inc()
        started = perf_counter()
        actor = f"worker:{self.worker_id}"
        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job, stop_heartbeat),
            name=f"geospatial-heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            with self.application.store.tenant_transaction(job.tenant_id, True):
                self.repository.heartbeat(job.tenant_id, job.id, self.worker_id)
            runner = {
                "NDVI": self.application.geospatial.run_ndvi_job,
                "QUALITY_MASKED_NDVI": self.application.geospatial.run_quality_masked_ndvi_job,
                "TEMPORAL_DELTA": self.application.geospatial.run_temporal_delta_job,
            }.get(job.job_type)
            if runner is None:
                raise ValueError("UNSUPPORTED_JOB_TYPE")
            result = runner(
                job.tenant_id,
                job.id,
                actor=actor,
                platform_admin=True,
                worker_id=self.worker_id,
            )
            final = result.job
        except Exception as exc:
            # Never serialize provider exception text: it can contain an endpoint or token.
            with self.application.store.tenant_transaction(job.tenant_id, True):
                final = self.repository.mark_job(
                    job.tenant_id,
                    job.id,
                    ProcessingJobStatus.FAILED,
                    failure_reason=type(exc).__name__,
                    failure_code=type(exc).__name__,
                    actor=actor,
                    worker_id=self.worker_id,
                )
            LOGGER.exception(
                "geospatial job failed",
                extra={"job_id": job.id, "tenant_id": job.tenant_id},
            )
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)
        JOB_DURATION.labels(job.job_type).observe(perf_counter() - started)
        if final.status in {
            ProcessingJobStatus.SUCCEEDED,
            ProcessingJobStatus.FAILED,
            ProcessingJobStatus.BLOCKED,
        }:
            JOB_OUTCOMES.labels(final.status.value).inc()
        self._refresh_metrics()
        return final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ribeira private geospatial job worker"
    )
    parser.add_argument("--once", action="store_true", help="process at most one job")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=int(os.getenv("RIBEIRA_GEOSPATIAL_STALE_AFTER_SECONDS", "3600")),
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=int(os.getenv("RIBEIRA_GEOSPATIAL_METRICS_PORT", "9109")),
        help="loopback Prometheus port; 0 disables the worker metrics endpoint",
    )
    args = parser.parse_args()
    if (
        args.poll_seconds <= 0
        or args.stale_after_seconds < 60
        or not 0 <= args.metrics_port <= 65535
    ):
        raise ValueError("invalid worker poll, stale timeout, or metrics port")
    settings = Settings.from_env()
    configure_structured_logging()
    application = RibeiraApplication(_build_store(settings))
    worker = GeospatialJobWorker(
        application,
        os.getenv(
            "RIBEIRA_GEOSPATIAL_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}"
        ),
        args.stale_after_seconds,
    )
    if args.metrics_port:
        start_http_server(args.metrics_port, addr="127.0.0.1")
        LOGGER.info("geospatial worker metrics listening on loopback")
    stop_requested = threading.Event()

    def request_stop(signum: int, _: object) -> None:
        LOGGER.info(
            "geospatial worker graceful shutdown requested",
            extra={"status": signal.Signals(signum).name},
        )
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while not stop_requested.is_set():
            job = worker.process_one()
            if args.once:
                return
            if job is None:
                stop_requested.wait(args.poll_seconds)
    finally:
        application.store.close()


if __name__ == "__main__":
    main()
