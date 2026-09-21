"""Bounded, evidence-first Sentinel-1 RTC flood-pilot primitives.

This module deliberately contains no tenant or customer semantics.  It builds
repeatable grids, validates analytical Process API responses, and keeps the
open-water classifier separate from any agronomic interpretation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from pyproj import CRS, Transformer
from rasterio.io import MemoryFile
from shapely.geometry import box, mapping, shape
from shapely.ops import transform


PROCESS_ENDPOINT = "https://sh.dataspace.copernicus.eu/process/v1"
TOKEN_ENDPOINT = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_VERSION = "sentinelhub-s1-rtc-v1"


@dataclass(frozen=True)
class SarTile:
    key: str
    x_index: int
    y_index: int
    bounds: tuple[float, float, float, float]
    geometry_wgs84: dict[str, Any]
    width: int
    height: int
    crs: str
    pixel_size_m: float

    @property
    def transform(self) -> tuple[float, float, float, float, float, float]:
        xmin, _ymin, _xmax, ymax = self.bounds
        return (self.pixel_size_m, 0.0, xmin, 0.0, -self.pixel_size_m, ymax)


def utm_crs_for_geometry(
    geometry: dict[str, Any], source_crs: str = "EPSG:4326"
) -> str:
    """Choose UTM from the actual centroid; never from a hard-coded municipality."""
    geom = shape(geometry)
    to_wgs84 = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True).transform
    centroid = transform(to_wgs84, geom).centroid
    zone = int(math.floor((centroid.x + 180.0) / 6.0) + 1)
    if not 1 <= zone <= 60:
        raise ValueError("geometry centroid cannot be assigned a UTM zone")
    return f"EPSG:{32700 + zone if centroid.y < 0 else 32600 + zone}"


def generate_intersecting_tiles(
    geometry: dict[str, Any],
    *,
    source_crs: str,
    target_crs: str,
    pixel_size_m: float = 20.0,
    tile_pixels: int = 1024,
) -> list[SarTile]:
    """Create a deterministic, origin-aligned grid pruned by polygon intersection."""
    if pixel_size_m <= 0 or tile_pixels <= 0:
        raise ValueError("pixel size and tile dimension must be positive")
    source = shape(geometry)
    if source.is_empty or not source.is_valid:
        raise ValueError("analysis AOI geometry must be valid and non-empty")
    forward = Transformer.from_crs(source_crs, target_crs, always_xy=True).transform
    inverse = Transformer.from_crs(target_crs, "EPSG:4326", always_xy=True).transform
    projected = transform(forward, source)
    tile_size = pixel_size_m * tile_pixels
    xmin, ymin, xmax, ymax = projected.bounds
    result: list[SarTile] = []
    for y_index in range(math.floor(ymin / tile_size), math.ceil(ymax / tile_size)):
        for x_index in range(math.floor(xmin / tile_size), math.ceil(xmax / tile_size)):
            tile_geometry = box(
                x_index * tile_size,
                y_index * tile_size,
                (x_index + 1) * tile_size,
                (y_index + 1) * tile_size,
            )
            if tile_geometry.intersection(projected).area <= 0:
                continue
            result.append(
                SarTile(
                    key=f"x{x_index}_y{y_index}",
                    x_index=x_index,
                    y_index=y_index,
                    bounds=tile_geometry.bounds,
                    geometry_wgs84=mapping(transform(inverse, tile_geometry)),
                    width=tile_pixels,
                    height=tile_pixels,
                    crs=target_crs,
                    pixel_size_m=pixel_size_m,
                )
            )
    return sorted(result, key=lambda item: (item.y_index, item.x_index))


def process_evalscript() -> str:
    """One five-band FLOAT32 response avoids one request per analytical band."""
    return """//VERSION=3
function setup() {
  return { input: [\"VV\", \"VH\", \"dataMask\", \"shadowMask\", \"localIncidenceAngle\"],
           output: { bands: 5, sampleType: \"FLOAT32\" } };
}
function evaluatePixel(s) {
  return [s.VV, s.VH, s.dataMask, s.shadowMask, s.localIncidenceAngle];
}"""


def build_process_request(
    *,
    tile: SarTile,
    acquired_at: datetime,
    orbit_direction: str,
    acquisition_mode: str,
    polarization: str,
) -> dict[str, Any]:
    """Build a tight, provider-neutral S1 GRD Process API request.

    Relative orbit has no documented Process API filter.  The caller must
    independently verify it in persisted catalogue metadata before requesting.
    """
    if acquired_at.tzinfo is None:
        raise ValueError("acquisition timestamp must be timezone aware")
    if (
        acquisition_mode != "IW"
        or orbit_direction != "DESCENDING"
        or polarization != "DV"
    ):
        raise ValueError("only the verified IW/DESCENDING/DV pilot contract is allowed")
    instant = acquired_at.astimezone(timezone.utc)
    begin = (instant - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    end = (instant + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    xmin, ymin, xmax, ymax = tile.bounds
    return {
        "input": {
            "bounds": {
                "bbox": [xmin, ymin, xmax, ymax],
                "properties": {
                    "crs": f"http://www.opengis.net/def/crs/EPSG/0/{tile.crs.split(':')[1]}"
                },
            },
            "data": [
                {
                    "type": "sentinel-1-grd",
                    "dataFilter": {
                        "timeRange": {"from": begin, "to": end},
                        "acquisitionMode": acquisition_mode,
                        "orbitDirection": orbit_direction,
                        "polarization": polarization,
                    },
                    "processing": {
                        "orthorectify": True,
                        "backCoeff": "GAMMA0_TERRAIN",
                        "demInstance": "COPERNICUS_30",
                    },
                }
            ],
        },
        "output": {
            "width": tile.width,
            "height": tile.height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": process_evalscript(),
    }


def payload_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_analytical_tiff(payload: bytes, tile: SarTile) -> None:
    """Reject visualization/empty/non-aligned Process API output."""
    with MemoryFile(payload) as memory:
        with memory.open() as dataset:
            if dataset.driver != "GTiff" or dataset.count != 5:
                raise ValueError(
                    "Process API did not return the required five-band GeoTIFF"
                )
            if dataset.crs != CRS.from_string(tile.crs):
                raise ValueError("Process API CRS differs from requested analysis grid")
            if (dataset.width, dataset.height) != (tile.width, tile.height):
                raise ValueError(
                    "Process API dimensions differ from requested analysis grid"
                )
            values = dataset.read([1, 2, 3, 4], out_dtype="float32")
            valid = values[2] > 0
            if not bool(valid.any()):
                raise ValueError("Process API tile has no valid dataMask pixels")
            if not bool(np.isfinite(values[:2, valid]).all()):
                raise ValueError("Process API RTC output has non-finite valid values")
            linear = values[:2, valid]
            if not bool((linear >= 0).all()) or not bool((linear > 0).any()):
                raise ValueError(
                    "Process API RTC output is not non-negative linear power"
                )


def linear_to_db(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    result = np.full(values.shape, np.nan, dtype="float32")
    use = valid & np.isfinite(values) & (values > 0)
    result[use] = 10.0 * np.log10(values[use])
    return result


def otsu_threshold(values: np.ndarray) -> float:
    samples = values[np.isfinite(values)]
    if samples.size < 32:
        raise ValueError("insufficient valid population for Otsu threshold")
    histogram, edges = np.histogram(samples, bins=256)
    weights = histogram.astype("float64")
    centres = (edges[:-1] + edges[1:]) / 2.0
    cumulative_weight = np.cumsum(weights)
    cumulative_mean = np.cumsum(weights * centres)
    total = cumulative_weight[-1]
    total_mean = cumulative_mean[-1]
    denominator = cumulative_weight * (total - cumulative_weight)
    between = np.divide(
        (total_mean * cumulative_weight - cumulative_mean) ** 2,
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )
    return float(centres[int(np.argmax(between))])


def sensitivity_masks(score: np.ndarray, central: float) -> dict[str, np.ndarray]:
    """Three explicit scenarios; lower score represents stronger open-water signal."""
    spread = float(np.nanstd(score))
    if not math.isfinite(spread) or spread <= 0:
        raise ValueError("threshold population has no usable spread")
    return {
        "CONSERVATIVE": np.isfinite(score) & (score <= central - 0.25 * spread),
        "CENTRAL": np.isfinite(score) & (score <= central),
        "PERMISSIVE": np.isfinite(score) & (score <= central + 0.25 * spread),
    }
