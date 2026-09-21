"""Private, idempotent ingestion of explicitly public Phase 1P.1 evidence."""

from __future__ import annotations

import argparse
import os

from .hydrology import ingest_public_evidence
from .postgres import PostgresStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest public hydrology evidence")
    parser.parse_args()
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise RuntimeError("RIBEIRA_DATABASE_URL is required")
    store = PostgresStore(dsn)
    try:
        with store.transaction():
            result = ingest_public_evidence(store)
        # Deliberately no URLs, body text, credentials, or identifiers in output.
        print("COPEL=" + str(result["COPEL"]))
        print("NOAA_CPC=" + str(result["NOAA_CPC"]))
        print("RESERVOIR_EVENTS=" + str(result["reservoir_events"]))
        print("CLIMATE_CONTEXT=" + str(result["climate_context"]))
    finally:
        store.close()


if __name__ == "__main__":
    main()
