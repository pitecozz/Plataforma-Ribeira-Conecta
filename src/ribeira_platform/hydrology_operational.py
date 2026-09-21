"""Bounded operational and historical WIS2 HTTP reconciliation."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

from .postgres import PostgresStore
from .vale_public_data import InmetWis2HttpProvider


def reconciliation_window(*, now: datetime, historical: bool, lookback_hours: int) -> tuple[datetime, datetime]:
    if now.tzinfo is None or not 3 <= lookback_hours <= 24:
        raise ValueError("invalid reconciliation window")
    end = now.astimezone(timezone.utc)
    return (
        datetime(2026, 9, 1, tzinfo=timezone.utc) if historical else end - timedelta(hours=lookback_hours),
        end,
    )


def _run(*, historical: bool, lookback_hours: int, max_pages: int, max_records: int) -> dict[str, int | str]:
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise RuntimeError("RIBEIRA_DATABASE_URL is required")
    started = datetime.now(timezone.utc)
    begin, end = reconciliation_window(now=started, historical=historical, lookback_hours=lookback_hours)
    context = "HISTORICAL_BACKFILL" if historical else "OPERATIONAL_RECONCILIATION"
    store = PostgresStore(dsn)
    received = inserted = duplicates = invalid = 0
    try:
        with store.transaction():
            bbox = store.vale_scope_envelope()
            provider = InmetWis2HttpProvider()
            try:
                datetime_range = f"{begin.isoformat().replace('+00:00','Z')}/{end.isoformat().replace('+00:00','Z')}"
                if historical:
                    records = []
                    examined = 0
                    bbox_supported = True
                    for station_identifier in store.wis2_station_identifiers():
                        station_records, station_examined, _ = provider.discover_rain(
                            bbox=None, station_identifier=station_identifier,
                            datetime_range=datetime_range, max_pages=max_pages,
                            max_records=max_records, page_size=200,
                        )
                        records.extend(station_records)
                        examined += station_examined
                else:
                    records, examined, bbox_supported = provider.discover_rain(
                        bbox=bbox, datetime_range=datetime_range, max_pages=max_pages,
                        max_records=max_records, page_size=200,
                    )
            except Exception as exc:
                finished = datetime.now(timezone.utc)
                store.upsert_source_health(
                    "INMET_WIS2_HTTP", "DEGRADED", last_attempt=finished.isoformat(),
                    latency_seconds=(finished - started).total_seconds(),
                    failure_code=type(exc).__name__, failure_detail_sanitized="bounded official WIS2 request failed",
                )
                store.record_hydro_ingestion_run(
                    context=context, started_at=started, finished_at=finished, status="DEGRADED",
                    received=0, inserted=0, duplicates=0, invalid=0, errors=1,
                    max_report_lag_seconds=None, detail="bounded official WIS2 request failed",
                )
                return {"STATUS": "DEGRADED", "ERROR": type(exc).__name__}
            for item in records:
                received += 1
                relation = store.station_scope_relation(longitude=item.longitude, latitude=item.latitude)
                if relation == "OUTSIDE_SCOPE" or item.raw_value is None:
                    invalid += 1
                    continue
                try:
                    station = store.upsert_wis2_station(item, relation=relation)
                    if store.record_wis2_rain(item, station_id=station, fetched_at=started):
                        inserted += 1
                    else:
                        duplicates += 1
                except (ValueError, RuntimeError):
                    invalid += 1
            finished = datetime.now(timezone.utc)
            lag = max(
                ((finished - item.report_time).total_seconds() for item in records),
                default=None,
            )
            store.upsert_source_health(
                "INMET_WIS2_HTTP", "AVAILABLE", last_attempt=finished.isoformat(),
                last_success=finished.isoformat(),
                last_observation=finished.isoformat() if received else None,
                latency_seconds=(finished - started).total_seconds(),
            )
            store.record_hydro_ingestion_run(
                context=context, started_at=started, finished_at=finished, status="SUCCESS",
                received=received, inserted=inserted, duplicates=duplicates, invalid=invalid,
                errors=0, max_report_lag_seconds=lag,
                detail="bbox " + ("accepted" if bbox_supported else "fallback"),
            )
            timeline = store.rebuild_september_event_timeline(end_at=end) if historical else {}
        return {
            "STATUS": "SUCCESS", "CONTEXT": context, "RECEIVED": received,
            "INSERTED": inserted, "DUPLICATES": duplicates, "INVALID": invalid,
            "RECORDS_EXAMINED": examined, "TIMELINE_ENTRIES": sum(timeline.values()),
        }
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded WIS2 HTTP reconciliation")
    parser.add_argument("--historical-backfill", action="store_true")
    parser.add_argument("--lookback-hours", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-records", type=int, default=2000)
    args = parser.parse_args()
    if not 3 <= args.lookback_hours <= 24 or not 1 <= args.max_pages <= 10 or not 1 <= args.max_records <= 2000:
        raise ValueError("unsafe reconciliation bounds")
    result = _run(
        historical=args.historical_backfill, lookback_hours=args.lookback_hours,
        max_pages=args.max_pages, max_records=args.max_records,
    )
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
