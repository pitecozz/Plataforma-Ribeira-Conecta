"""Private catalogue-only command that locks a Registro Sentinel-1 pair."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any

from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

from .flood_sar import generate_intersecting_tiles
from .geospatial import SatelliteSearchRequest, SceneSelectionPolicy
from .geospatial_provider import (
    CopernicusStacAdapter,
    CopernicusStacConfig,
    default_copernicus_registry,
)
from .models import new_id
from .postgres import PostgresStore
from .sentinel1_discovery import (
    METRIC_CRS,
    SOURCE_CRS,
    EventWindow,
    PairAssessment,
    SceneAssessment,
    assess_scene,
    build_pairs,
    derive_event_window,
    search_window,
)


EVENT_KEY = "VALE_RIBEIRA_FLOOD_2026_09"
AOI_KEY = "VALE_FLOOD_2026_09_REGISTRO_PILOT"
REGISTRO_CODE = "3542602"
COLLECTION = "sentinel-1-grd"
CATALOG = "https://stac.dataspace.copernicus.eu/v1/"


def _store() -> PostgresStore:
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise RuntimeError("RIBEIRA_DATABASE_URL is required")
    return PostgresStore(dsn)


def _registro_context(store: PostgresStore) -> tuple[dict[str, Any], dict[str, Any]]:
    row = store.connection.execute(
        """SELECT a.id AS aoi_id,e.id AS event_id,ST_AsGeoJSON(m.geometry) AS geometry,
                  m.source_reference,m.source_sha256,ST_IsValid(m.geometry) AS geometry_valid
             FROM event_analysis_aoi a
             JOIN municipality_reference m ON m.id=a.municipality_id
             JOIN operational_event e ON e.id=a.event_id
            WHERE a.aoi_key=%s AND m.ibge_code=%s AND m.uf='SP' AND m.source_year=2025""",
        (AOI_KEY, REGISTRO_CODE),
    ).fetchone()
    if row is None or not row["geometry_valid"] or len(str(row["source_sha256"])) != 64:
        raise RuntimeError(
            "official valid Registro geometry and provenance are required"
        )
    return dict(row), json.loads(row["geometry"])


def _event_window(store: PostgresStore, event_id: str, aoi_id: str) -> EventWindow:
    rows = store.connection.execute(
        """SELECT event_type,occurred_at,detail
             FROM operational_event_timeline_entry WHERE event_id=%s
               AND event_type IN ('RESERVOIR_OPERATION','RAINFALL_ACCUMULATION_PEAK')
             UNION ALL
           SELECT 'EVENT_PRIORITY',observed_at,detail
             FROM event_analysis_aoi_evidence WHERE aoi_id=%s AND evidence_type='EVENT_PRIORITY'
             ORDER BY 2""",
        (event_id, aoi_id),
    ).fetchall()
    return derive_event_window([dict(row) for row in rows])


def _adapter() -> CopernicusStacAdapter:
    config = CopernicusStacConfig(collection_id=COLLECTION, max_pages=4)
    return CopernicusStacAdapter(default_copernicus_registry(config), config)


def _validate_contract(adapter: CopernicusStacAdapter) -> list[str]:
    queryables = adapter._request_json(
        "GET", adapter._url(f"collections/{COLLECTION}/queryables")
    )
    properties = queryables.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("CDSE collection queryables response is malformed")
    required = {
        "datetime",
        "geometry",
        "sar:instrument_mode",
        "sat:orbit_state",
        "sar:polarizations",
        "sat:relative_orbit",
        "product:type",
    }
    missing = required - set(properties)
    if missing:
        raise RuntimeError(
            f"CDSE queryables missing expected contract fields: {sorted(missing)}"
        )
    return sorted(properties)


def _persist_scene(store: PostgresStore, event_id: str, item: dict[str, Any]) -> str:
    properties = item["properties"]
    row = store.connection.execute(
        """INSERT INTO satellite_event_scene_evidence(
                 id,event_id,provider,collection_id,provider_record_id,acquired_at,geometry,
                 metadata,source_reference,classification
               ) VALUES (%s,%s,'COPERNICUS_CDSE',%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s::jsonb,%s,'OFFICIAL_SOURCE')
               ON CONFLICT (event_id,provider,collection_id,provider_record_id) DO UPDATE
                 SET acquired_at=EXCLUDED.acquired_at,geometry=EXCLUDED.geometry,metadata=EXCLUDED.metadata,
                     source_reference=EXCLUDED.source_reference
               RETURNING id""",
        (
            new_id(),
            event_id,
            COLLECTION,
            item["id"],
            properties["datetime"],
            json.dumps(item["geometry"]),
            json.dumps(properties),
            f"{CATALOG}search",
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("scene persistence did not return an identifier")
    return str(row["id"])


def _persist_assessment(
    store: PostgresStore,
    aoi_id: str,
    scene_id: str,
    item: SceneAssessment,
    provenance: dict[str, Any],
) -> None:
    store.connection.execute(
        """INSERT INTO event_sar_scene_assessment(
                 id,aoi_id,scene_evidence_id,registro_coverage_km2,registro_coverage_percent,
                 pre_classification,event_classification,assessment,provenance
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
               ON CONFLICT (aoi_id,scene_evidence_id) DO UPDATE SET
                 registro_coverage_km2=EXCLUDED.registro_coverage_km2,registro_coverage_percent=EXCLUDED.registro_coverage_percent,
                 pre_classification=EXCLUDED.pre_classification,event_classification=EXCLUDED.event_classification,
                 assessment=EXCLUDED.assessment,provenance=EXCLUDED.provenance,updated_at=now()""",
        (
            new_id(),
            aoi_id,
            scene_id,
            item.coverage_km2,
            item.coverage_percent,
            item.pre_classification,
            item.event_classification,
            json.dumps(
                {
                    "pre_reason": item.pre_reason,
                    "event_reason": item.event_reason,
                    "platform": item.platform,
                    "product_type": item.product_type,
                    "absolute_orbit": item.absolute_orbit,
                    "instrument_mode": item.scene.mode,
                    "orbit_direction": item.scene.orbit_state,
                    "relative_orbit": item.scene.relative_orbit,
                    "polarizations": item.scene.polarizations,
                }
            ),
            json.dumps(provenance),
        ),
    )


def _persist_pair(
    store: PostgresStore,
    aoi_id: str,
    scene_ids: dict[str, str],
    pair: PairAssessment,
    status: str,
    provenance: dict[str, Any],
) -> None:
    key = f"REGISTRO_S1_PAIR_V2_{pair.pre.scene.provider_record_id}_{pair.event.scene.provider_record_id}"
    store.connection.execute(
        """INSERT INTO event_sar_pair_selection(
                 id,aoi_id,pair_key,pre_scene_evidence_id,event_scene_evidence_id,status,common_geometry,
                 pre_registro_coverage_km2,event_registro_coverage_km2,common_registro_coverage_km2,
                 common_registro_coverage_percent,rank_order,selection_reason,compatibility,provenance
               ) VALUES (%s,%s,%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4674),%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
               ON CONFLICT (aoi_id,pair_key) DO UPDATE SET status=EXCLUDED.status,common_geometry=EXCLUDED.common_geometry,
                 pre_registro_coverage_km2=EXCLUDED.pre_registro_coverage_km2,event_registro_coverage_km2=EXCLUDED.event_registro_coverage_km2,
                 common_registro_coverage_km2=EXCLUDED.common_registro_coverage_km2,common_registro_coverage_percent=EXCLUDED.common_registro_coverage_percent,
                 rank_order=EXCLUDED.rank_order,selection_reason=EXCLUDED.selection_reason,compatibility=EXCLUDED.compatibility,
                 provenance=EXCLUDED.provenance,updated_at=now()""",
        (
            new_id(),
            aoi_id,
            key,
            scene_ids[pair.pre.scene.provider_record_id],
            scene_ids[pair.event.scene.provider_record_id],
            status,
            json.dumps(pair.common_geometry),
            pair.pre.coverage_km2,
            pair.event.coverage_km2,
            pair.common_coverage_km2,
            pair.common_coverage_percent,
            pair.rank_order,
            "ranked by nonzero/high common coverage, exact SAR compatibility, event relevance, pre-event validity, interval, VV/VH",
            json.dumps(
                {
                    "instrument_mode": pair.pre.scene.mode,
                    "orbit_direction": pair.pre.scene.orbit_state,
                    "relative_orbit": pair.pre.scene.relative_orbit,
                    "polarizations": pair.pre.scene.polarizations,
                    "product_type": pair.pre.product_type,
                    "same_platform": pair.pre.platform == pair.event.platform,
                    "pre_to_event_days": pair.pre_to_event_days,
                    "event_offset_from_window_start_days": pair.event_offset_days,
                }
            ),
            json.dumps(provenance),
        ),
    )


def _mark_old_pair(store: PostgresStore, aoi_id: str) -> None:
    ids = store.connection.execute(
        """SELECT provider_record_id,id FROM satellite_event_scene_evidence
             WHERE event_id=(SELECT id FROM operational_event WHERE event_key=%s)
               AND provider_record_id IN (%s,%s)""",
        (
            EVENT_KEY,
            "S1D_IW_GRDH_1SDV_20260907T083051_20260907T083116_004469_00849D_8C6B_COG",
            "S1C_IW_GRDH_1SDV_20260913T083025_20260913T083050_009426_012BFA_AC72_COG",
        ),
    ).fetchall()
    found = {str(row["provider_record_id"]): str(row["id"]) for row in ids}
    if len(found) != 2:
        return
    store.connection.execute(
        """INSERT INTO event_sar_pair_selection(id,aoi_id,pair_key,pre_scene_evidence_id,event_scene_evidence_id,status,
                 pre_registro_coverage_km2,event_registro_coverage_km2,common_registro_coverage_km2,common_registro_coverage_percent,
                 selection_reason,compatibility,provenance)
               VALUES (%s,%s,'REGISTRO_S1_PAIR_V1_20260907_20260913',%s,%s,'NO_SPATIAL_COVERAGE',0,0,0,0,
                 'official scene footprint intersection with Registro is zero',%s::jsonb,%s::jsonb)
               ON CONFLICT (aoi_id,pair_key) DO UPDATE SET status='NO_SPATIAL_COVERAGE',selection_reason=EXCLUDED.selection_reason,
                 provenance=EXCLUDED.provenance,updated_at=now()""",
        (
            new_id(),
            aoi_id,
            found[
                "S1D_IW_GRDH_1SDV_20260907T083051_20260907T083116_004469_00849D_8C6B_COG"
            ],
            found[
                "S1C_IW_GRDH_1SDV_20260913T083025_20260913T083050_009426_012BFA_AC72_COG"
            ],
            json.dumps(
                {
                    "instrument_mode": "IW",
                    "orbit_direction": "descending",
                    "relative_orbit": 53,
                    "polarizations": ["VV", "VH"],
                }
            ),
            json.dumps(
                {
                    "classification": "NOT_APPLICABLE_TO_REGISTRO_PILOT",
                    "reason": "official_scene_footprint_intersection_registro_equals_zero",
                }
            ),
        ),
    )
    store.connection.execute(
        """UPDATE event_flood_analysis SET status='INCONCLUSIVE',evidence_status='INCONCLUSIVE',
                 limitations=limitations || %s::jsonb,updated_at=now()
             WHERE aoi_id=%s""",
        (
            json.dumps(
                [
                    "INVALID_PREVIOUS_REGISTRO_PAIR_NO_SPATIAL_COVERAGE; retained only as provenance"
                ]
            ),
            aoi_id,
        ),
    )
    store.connection.execute(
        """UPDATE event_sar_asset SET metadata=metadata || %s::jsonb
             WHERE scene_evidence_id=ANY(%s)""",
        (
            json.dumps(
                {
                    "valid_for_registro_pilot": False,
                    "invalidation_reason": "NO_SPATIAL_COVERAGE",
                }
            ),
            list(found.values()),
        ),
    )


def _tile_plan(pair: PairAssessment) -> tuple[int, str, float]:
    tiles = generate_intersecting_tiles(
        pair.common_geometry, source_crs=SOURCE_CRS, target_crs=METRIC_CRS
    )
    inverse = Transformer.from_crs(SOURCE_CRS, METRIC_CRS, always_xy=True).transform
    common = transform(inverse, shape(pair.common_geometry))
    best = max(
        tiles,
        key=lambda tile: transform(inverse, shape(tile.geometry_wgs84))
        .intersection(common)
        .area,
    )
    coverage = (
        transform(inverse, shape(best.geometry_wgs84)).intersection(common).area
        / common.area
        * 100
    )
    return len(tiles), best.key, coverage


def discover() -> dict[str, Any]:
    store = _store()
    try:
        with store.tenant_transaction(None, platform_admin=True):
            context, registro = _registro_context(store)
            window = _event_window(
                store, str(context["event_id"]), str(context["aoi_id"])
            )
            search_start, search_end = search_window(window)
            adapter = _adapter()
            queryables = _validate_contract(adapter)
            result = adapter.search(
                SatelliteSearchRequest(
                    property_id="REGISTRO_OFFICIAL_2025",
                    collection_id=COLLECTION,
                    datetime_start=search_start.isoformat().replace("+00:00", "Z"),
                    datetime_end=search_end.isoformat().replace("+00:00", "Z"),
                    selection_policy=SceneSelectionPolicy(max_candidates=100),
                ),
                registro,
            )
            assessments = [
                assess_scene(item, registro, window) for item in result.items
            ]
            assessments = [item for item in assessments if item.coverage_km2 > 0]
            pairs = build_pairs(assessments, registro, window)
            provenance = {
                "generated_at": datetime.now().astimezone().isoformat(),
                "catalog_endpoint": CATALOG,
                "collection": COLLECTION,
                "spatial_query": "STAC intersects=official persisted Registro polygon",
                "queryables": queryables,
                "event_window": {
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                },
                "registro_geometry_checksum": context["source_sha256"],
                "registro_source_reference": context["source_reference"],
                "process_api_requests_new": 0,
            }
            scene_ids: dict[str, str] = {}
            by_id = {item["id"]: item for item in result.items}
            for assessment in assessments:
                scene_ids[assessment.scene.provider_record_id] = _persist_scene(
                    store,
                    str(context["event_id"]),
                    by_id[assessment.scene.provider_record_id],
                )
                _persist_assessment(
                    store,
                    str(context["aoi_id"]),
                    scene_ids[assessment.scene.provider_record_id],
                    assessment,
                    provenance,
                )
            _mark_old_pair(store, str(context["aoi_id"]))
            for pair in pairs:
                _persist_pair(
                    store,
                    str(context["aoi_id"]),
                    scene_ids,
                    pair,
                    "SELECTED" if pair.rank_order == 1 else "CANDIDATE",
                    provenance,
                )
            if not pairs:
                return {
                    "registro_s1_pair_v2": "NONE",
                    "event_window": window,
                    "search_start": search_start,
                    "search_end": search_end,
                    "scenes": len(assessments),
                    "pairs": 0,
                    "process_api_requests_new": 0,
                }
            best = pairs[0]
            tiles, validation_tile, validation_coverage = _tile_plan(best)
            store.connection.execute(
                """UPDATE event_sar_pair_selection SET provenance=provenance || %s::jsonb,updated_at=now()
                WHERE aoi_id=%s AND rank_order=1 AND status='SELECTED'""",
                (
                    json.dumps(
                        {
                            "tile_plan": {
                                "crs": METRIC_CRS,
                                "resolution_m": 20,
                                "common_analysis_area_km2": best.common_coverage_km2,
                                "tiles_intersecting_common_area": tiles,
                                "planned_requests_per_scene": tiles,
                                "planned_total_requests": tiles * 2,
                                "validation_tile_v3": validation_tile,
                                "validation_tile_v3_common_coverage_percent": validation_coverage,
                            }
                        }
                    ),
                    context["aoi_id"],
                ),
            )
            return {
                "registro_s1_pair_v2": "SELECTED",
                "event_window": window,
                "search_start": search_start,
                "search_end": search_end,
                "scenes": len(assessments),
                "pairs": len(pairs),
                "best": best,
                "tiles": tiles,
                "validation_tile": validation_tile,
                "validation_coverage": validation_coverage,
                "process_api_requests_new": 0,
            }
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover a Registro-covering Sentinel-1 pair without Process API"
    )
    parser.add_argument("command", choices=("discover",))
    parser.parse_args()
    result = discover()
    print(
        json.dumps(
            result,
            default=lambda value: value.__dict__
            if hasattr(value, "__dict__")
            else value.isoformat(),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
