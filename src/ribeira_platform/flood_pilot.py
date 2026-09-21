"""Private operator command for the bounded Registro Sentinel-1 pilot."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.shutil import copy as rio_copy
from shapely.geometry import shape

from .flood_sar import (
    PROCESS_VERSION,
    SarTile,
    build_process_request,
    generate_intersecting_tiles,
    payload_fingerprint,
    utm_crs_for_geometry,
    validate_analytical_tiff,
)
from .models import new_id
from .object_storage import LocalObjectStorage
from .postgres import PostgresStore
from .sentinelhub_client import SentinelHubClient, load_private_credentials


EVENT_KEY = "VALE_RIBEIRA_FLOOD_2026_09"
AOI_KEY = "VALE_FLOOD_2026_09_REGISTRO_PILOT"
REGISTRO_CODE = "3542602"
EVENT_EVIDENCE_URL = "https://registro.sp.gov.br/defesa-civil-de-registro-intensifica-acoes-de-atendimento-as-familias-afetadas-pelas-enchentes/"
PIXEL_SIZE_M = 20.0
TILE_PIXELS = 1024


def _store() -> PostgresStore:
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise RuntimeError("RIBEIRA_DATABASE_URL is required")
    return PostgresStore(dsn)


def _registro_aoi(
    store: PostgresStore,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    row = store.connection.execute(
        """SELECT m.id AS municipality_id, e.id AS event_id,
                  ST_AsGeoJSON(m.geometry) AS geometry, m.source_reference,
                  m.source_sha256, ST_IsValid(m.geometry) AS geometry_valid,
                  ST_SRID(m.geometry) AS geometry_crs
             FROM municipality_reference m
             CROSS JOIN operational_event e
            WHERE m.ibge_code=%s AND m.uf='SP' AND m.source_year=2025
              AND e.event_key=%s""",
        (REGISTRO_CODE, EVENT_KEY),
    ).fetchone()
    if row is None or not row["geometry_valid"] or row["geometry_crs"] != 4674:
        raise RuntimeError(
            "verified official Registro municipality geometry is unavailable"
        )
    geometry = json.loads(row["geometry"])
    checksum = str(row["source_sha256"])
    if len(checksum) != 64:
        raise RuntimeError("Registro official geometry checksum is unavailable")
    return (
        row,
        geometry,
        {"geometry_checksum": checksum, "source_reference": row["source_reference"]},
    )


def prepare() -> dict[str, int | str]:
    store = _store()
    try:
        with store.tenant_transaction(None, platform_admin=True):
            ref, geometry, source = _registro_aoi(store)
            target_crs = utm_crs_for_geometry(geometry, "EPSG:4674")
            tiles = generate_intersecting_tiles(
                geometry,
                source_crs="EPSG:4674",
                target_crs=target_crs,
                pixel_size_m=PIXEL_SIZE_M,
                tile_pixels=TILE_PIXELS,
            )
            if len(tiles) > 25:
                raise RuntimeError(
                    "Registro pilot exceeds the approved per-scene tile gate"
                )
            aoi = store.connection.execute(
                """INSERT INTO event_analysis_aoi(
                       id,event_id,municipality_id,aoi_key,geometry,geometry_checksum,
                       source_reference,classification,provenance
                     ) VALUES (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4674),%s,%s,'DERIVED',%s::jsonb)
                     ON CONFLICT (aoi_key) DO UPDATE SET provenance=EXCLUDED.provenance
                     RETURNING id""",
                (
                    new_id(),
                    ref["event_id"],
                    ref["municipality_id"],
                    AOI_KEY,
                    json.dumps(geometry),
                    source["geometry_checksum"],
                    source["source_reference"],
                    json.dumps(
                        {
                            "method": "official_ibge_2025_municipality_geometry",
                            "municipality_code": REGISTRO_CODE,
                            "source_crs": "EPSG:4674",
                            "target_grid_crs": target_crs,
                            "classification": "DERIVED_SCOPE",
                        }
                    ),
                ),
            ).fetchone()
            if aoi is None:
                raise RuntimeError("could not persist Registro event analysis AOI")
            aoi_id = aoi["id"]
            store.connection.execute(
                """INSERT INTO event_analysis_aoi_evidence(
                       id,aoi_id,evidence_type,source_reference,observed_at,retrieved_at,classification,detail
                     ) VALUES (%s,%s,'EVENT_PRIORITY',%s,%s,now(),'OFFICIAL_SOURCE',%s::jsonb)
                     ON CONFLICT (aoi_id,evidence_type,source_reference) DO NOTHING""",
                (
                    new_id(),
                    aoi_id,
                    EVENT_EVIDENCE_URL,
                    "2026-09-14T00:00:00Z",
                    json.dumps(
                        {
                            "reported_affected_locations": 23,
                            "scope_semantics": "textual official event-priority evidence; not a flood geometry",
                        }
                    ),
                ),
            )
            for tile in tiles:
                store.connection.execute(
                    """INSERT INTO event_sar_tile(
                           id,aoi_id,tile_key,geometry,grid_crs,grid_transform,width,height,pixel_size_m
                         ) VALUES (%s,%s,%s,ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674),%s,%s::jsonb,%s,%s,%s)
                         ON CONFLICT (aoi_id,tile_key) DO NOTHING""",
                    (
                        new_id(),
                        aoi_id,
                        tile.key,
                        json.dumps(tile.geometry_wgs84),
                        target_crs,
                        json.dumps(tile.transform),
                        tile.width,
                        tile.height,
                        tile.pixel_size_m,
                    ),
                )
            store.connection.execute(
                """INSERT INTO event_flood_analysis(id,aoi_id,status,evidence_status,parameters,limitations)
                   VALUES (%s,%s,'PREPARED','INCONCLUSIVE',%s::jsonb,%s::jsonb)
                   ON CONFLICT (aoi_id) DO NOTHING""",
                (
                    new_id(),
                    aoi_id,
                    json.dumps(
                        {
                            "processing_version": PROCESS_VERSION,
                            "pixel_size_m": PIXEL_SIZE_M,
                            "tile_pixels": TILE_PIXELS,
                        }
                    ),
                    json.dumps(
                        [
                            "OPEN_WATER_ONLY",
                            "VEGETATED_INUNDATION_NOT_ASSESSED",
                            "MUNICIPAL_PILOT_NOT_COMPLETE_VALE",
                            "ANA_RIVER_STAGE_PENDING",
                            "SAISP_AUTOMATION_UNAVAILABLE",
                        ]
                    ),
                ),
            )
        return {
            "aoi": AOI_KEY,
            "crs": target_crs,
            "tiles": len(tiles),
            "requests": len(tiles) * 2,
        }
    finally:
        store.close()


def _scenes(store: PostgresStore) -> dict[str, dict[str, Any]]:
    rows = store.connection.execute(
        """SELECT id,provider_record_id,acquired_at,ST_AsGeoJSON(geometry) AS geometry,metadata
             FROM satellite_event_scene_evidence
            WHERE event_id=(SELECT id FROM operational_event WHERE event_key=%s)
            ORDER BY acquired_at""",
        (EVENT_KEY,),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = row["metadata"] or {}
        match = (
            str(metadata.get("instrument_mode", "")).upper() == "IW"
            and str(metadata.get("orbit_state", "")).upper() == "DESCENDING"
            and str(metadata.get("relative_orbit", "")) == "53"
            and sorted(metadata.get("polarizations") or []) == ["VH", "VV"]
        )
        if not match:
            continue
        role = (
            "PRE"
            if row["acquired_at"].date().isoformat() == "2026-09-07"
            else "EVENT"
            if row["acquired_at"].date().isoformat() == "2026-09-13"
            else None
        )
        if role:
            result[role] = {**dict(row), "geometry": json.loads(row["geometry"])}
    if set(result) != {"PRE", "EVENT"}:
        raise RuntimeError("exact verified Sentinel-1 PRE/EVENT pair is unavailable")
    return result


def _to_cog(
    storage: LocalObjectStorage,
    *,
    payload: bytes,
    band: int,
    role: str,
    name: str,
    tile: SarTile,
) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="ribeira-sar-") as temporary:
        source_path = Path(temporary) / "source.tif"
        target_path = Path(temporary) / "asset.tif"
        source_path.write_bytes(payload)
        with rasterio.open(source_path) as source:
            data = source.read(band)
            is_mask = name in {"DATA_MASK", "SHADOW_MASK"}
            profile = source.profile.copy()
            profile.update(
                count=1,
                dtype="uint8" if is_mask else "float32",
                nodata=0 if is_mask else np.nan,
            )
            with rasterio.open(target_path, "w", **profile) as destination:
                destination.write(
                    (data > 0).astype("uint8") if is_mask else data.astype("float32"), 1
                )
        cog_path = Path(temporary) / "asset-cog.tif"
        rio_copy(target_path, cog_path, driver="COG", compress="DEFLATE", blocksize=512)
        key = f"flood/vale-ribeira-2026-09/registro/{tile.key}/{role}-{name}.tif"
        reference, checksum, _size = storage.put_file(
            key, cog_path, media_type="image/tiff"
        )
    return reference, checksum


def single_tile() -> dict[str, str]:
    store = _store()
    try:
        with store.tenant_transaction(None, platform_admin=True):
            aoi = store.connection.execute(
                "SELECT id FROM event_analysis_aoi WHERE aoi_key=%s", (AOI_KEY,)
            ).fetchone()
            if aoi is None:
                raise RuntimeError("prepare must run before single-tile processing")
            scenes = _scenes(store)
            tiles = store.connection.execute(
                """SELECT id,tile_key,ST_AsGeoJSON(ST_Transform(geometry,4326)) AS geometry,grid_crs,grid_transform,width,height,pixel_size_m
                     FROM event_sar_tile WHERE aoi_id=%s ORDER BY tile_key""",
                (aoi["id"],),
            ).fetchall()
            selected = None
            for row in tiles:
                candidate_geom = shape(json.loads(row["geometry"]))
                if all(
                    candidate_geom.intersection(shape(scene["geometry"])).area > 0
                    for scene in scenes.values()
                ):
                    selected = row
                    break
            if selected is None:
                raise RuntimeError(
                    "no Registro tile intersects both verified Sentinel-1 scene footprints"
                )
            bounds = shape(json.loads(selected["geometry"])).bounds
            tile = SarTile(
                str(selected["tile_key"]),
                0,
                0,
                bounds,
                json.loads(selected["geometry"]),
                int(selected["width"]),
                int(selected["height"]),
                str(selected["grid_crs"]),
                float(selected["pixel_size_m"]),
            )
            # bounds above are WGS84, while the Process request requires projected bounds. Recover from stored affine transform.
            transform_values = selected["grid_transform"]
            if isinstance(transform_values, str):
                transform_values = json.loads(transform_values)
            if not isinstance(transform_values, list) or len(transform_values) != 6:
                raise RuntimeError("persisted tile grid transform is invalid")
            tile = SarTile(
                tile.key,
                0,
                0,
                (
                    transform_values[2],
                    transform_values[5] + transform_values[4] * tile.height,
                    transform_values[2] + transform_values[0] * tile.width,
                    transform_values[5],
                ),
                tile.geometry_wgs84,
                tile.width,
                tile.height,
                tile.crs,
                tile.pixel_size_m,
            )
        client = SentinelHubClient(
            load_private_credentials(
                Path.home() / ".config/ribeira/cdse-sentinelhub.env"
            )
        )
        storage = LocalObjectStorage()
        for role in ("PRE", "EVENT"):
            scene = scenes[role]
            payload = build_process_request(
                tile=tile,
                acquired_at=scene["acquired_at"],
                orbit_direction="DESCENDING",
                acquisition_mode="IW",
                polarization="DV",
            )
            response = client.process(payload)
            validate_analytical_tiff(response, tile)
            assets = [
                ("VV_RTC_LINEAR_POWER", 1, "VV_RTC_LINEAR_POWER"),
                ("VH_RTC_LINEAR_POWER", 2, "VH_RTC_LINEAR_POWER"),
                ("DATA_MASK", 3, "DATA_MASK"),
                ("SHADOW_MASK", 4, "SHADOW_MASK"),
                ("LOCAL_INCIDENCE_ANGLE", 5, "LOCAL_INCIDENCE_ANGLE"),
            ]
            persisted = [
                (
                    _type,
                    *_to_cog(
                        storage,
                        payload=response,
                        band=band,
                        role=role,
                        name=name,
                        tile=tile,
                    ),
                )
                for _type, band, name in assets
            ]
            with store.tenant_transaction(None, platform_admin=True):
                for asset_type, reference, checksum in persisted:
                    store.connection.execute(
                        """INSERT INTO event_sar_asset(id,tile_id,scene_evidence_id,acquisition_role,asset_type,storage_reference,sha256,metadata)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                           ON CONFLICT (tile_id,scene_evidence_id,asset_type) DO NOTHING""",
                        (
                            new_id(),
                            selected["id"],
                            scene["id"],
                            role,
                            asset_type,
                            reference,
                            checksum,
                            json.dumps(
                                {
                                    "processing_version": PROCESS_VERSION,
                                    "payload_sha256": payload_fingerprint(payload),
                                    "backscatter_coefficient": "GAMMA0_TERRAIN",
                                    "orthorectified": True,
                                    "dem": "COPERNICUS_30",
                                    "grid_crs": tile.crs,
                                    "pixel_size_m": tile.pixel_size_m,
                                }
                            ),
                        ),
                    )
        return {"tile": tile.key, "status": "VERIFIED"}
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Private bounded Registro Sentinel-1 flood pilot"
    )
    parser.add_argument("command", choices=("prepare", "single-tile"))
    args = parser.parse_args()
    result = prepare() if args.command == "prepare" else single_tile()
    print(" ".join(f"{key.upper()}={value}" for key, value in result.items()))


if __name__ == "__main__":
    main()
