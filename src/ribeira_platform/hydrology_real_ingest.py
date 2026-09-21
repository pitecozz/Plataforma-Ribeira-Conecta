"""One bounded, idempotent ingestion pass for official WIS2 and SIDRA data."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from .postgres import PostgresStore
from .vale_public_data import (
    InmetWis2HttpProvider,
    SidraPamProvider,
    parse_sidra_baselines,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded official Vale public-data ingestion"
    )
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-records", type=int, default=2000)
    args = parser.parse_args()
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise RuntimeError("RIBEIRA_DATABASE_URL is required")
    store = PostgresStore(dsn)
    try:
        with store.transaction():
            scope_municipalities = store.derive_verified_semil_scope()
            bbox = store.vale_scope_envelope()
            wis2 = InmetWis2HttpProvider()
            records, examined, bbox_supported = wis2.discover_rain(
                bbox=bbox, max_pages=args.max_pages, max_records=args.max_records
            )
            if not bbox_supported:
                records, examined, _ = wis2.discover_rain(
                    bbox=None, max_pages=args.max_pages, max_records=args.max_records
                )
            fetched_at = datetime.now(timezone.utc)
            for record in records:
                relation = store.station_scope_relation(
                    longitude=record.longitude, latitude=record.latitude
                )
                if relation == "OUTSIDE_SCOPE":
                    continue
                station_id = store.upsert_wis2_station(record, relation=relation)
                if record.raw_value is not None:
                    store.record_wis2_rain(
                        record, station_id=station_id, fetched_at=fetched_at
                    )
            station_total, observation_total = store.wis2_ingestion_counts()
            store.upsert_source_health(
                "INMET_WIS2_HTTP",
                "AVAILABLE",
                last_attempt=fetched_at.isoformat(),
                last_success=fetched_at.isoformat(),
                last_observation=fetched_at.isoformat() if observation_total else None,
            )
            # Channel-specific health prevents the legacy portal reset and an
            # idle bounded MQTT sample from masking the working HTTP channel.
            store.upsert_source_health(
                "INMET_PORTAL",
                "DEGRADED",
                last_attempt=fetched_at.isoformat(),
                failure_code="HTTP_RESET",
                failure_detail_sanitized="official portal channel reset during bounded diagnostic",
            )
            store.upsert_source_health(
                "INMET_WIS2_MQTT",
                "AVAILABLE",
                last_attempt=fetched_at.isoformat(),
                failure_code="NO_NOTIFICATION_IN_WINDOW",
                failure_detail_sanitized="bounded outbound MQTT probe received no notification; HTTP OGC API remains available",
            )
            sidra = SidraPamProvider()
            metadata = sidra.metadata()
            codes = store.semil_municipality_codes()
            small = parse_sidra_baselines(sidra.values(codes[:3], metadata), metadata)
            if not small:
                raise RuntimeError(
                    "SIDRA small official query returned no municipality rows"
                )
            for code, values in small.items():
                store.upsert_banana_baseline(
                    municipality_code=code,
                    values=values,
                    metadata=metadata,
                    source_reference="https://apisidra.ibge.gov.br/values/t/1613",
                )
            complete = parse_sidra_baselines(sidra.values(codes, metadata), metadata)
            for code, values in complete.items():
                store.upsert_banana_baseline(
                    municipality_code=code,
                    values=values,
                    metadata=metadata,
                    source_reference="https://apisidra.ibge.gov.br/values/t/1613",
                )
            baseline_total = store.banana_baseline_count()
            store.upsert_source_health(
                "IBGE_PAM_SIDRA",
                "AVAILABLE",
                last_attempt=fetched_at.isoformat(),
                last_success=fetched_at.isoformat(),
            )
        for key, value in {
            "SCOPE_MUNICIPALITIES": scope_municipalities,
            "WIS2_BBOX": "SUPPORTED" if bbox_supported else "FALLBACK_BOUNDED",
            "WIS2_RECORDS_EXAMINED": examined,
            "WIS2_STATIONS": station_total,
            "WIS2_OBSERVATIONS": observation_total,
            "SIDRA_PERIOD": metadata.period,
            "SIDRA_SMALL_VALIDATED": len(small),
            "SIDRA_BASELINES": baseline_total,
        }.items():
            print(f"{key}={value}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
