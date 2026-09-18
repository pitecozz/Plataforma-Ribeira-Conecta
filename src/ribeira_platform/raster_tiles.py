from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds


class InvalidTile(ValueError):
    pass


class RasterUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class RasterTile:
    payload: bytes
    has_data: bool


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    if not 0 <= z <= 22:
        raise InvalidTile("tile zoom must be between 0 and 22")
    limit = 1 << z
    if not 0 <= x < limit or not 0 <= y < limit:
        raise InvalidTile("tile coordinates are outside the zoom range")
    extent = 20037508.342789244
    span = (extent * 2) / limit
    west = -extent + x * span
    east = west + span
    north = extent - y * span
    south = north - span
    return west, south, east, north


def _colourize(values: np.ndarray) -> np.ndarray:
    """A display-only brown/yellow/green NDVI ramp; source values stay untouched."""
    rgba = np.zeros((4, values.shape[0], values.shape[1]), dtype="uint8")
    valid = np.isfinite(values)
    normalized = np.clip((values + 1.0) / 2.0, 0.0, 1.0)
    # Linear interpolation keeps the palette deterministic and separate from science.
    stops = np.array([[140, 81, 10], [247, 247, 247], [0, 104, 55]], dtype="float32")
    lower = normalized <= 0.5
    high = ~lower
    ratio_low = normalized * 2.0
    ratio_high = (normalized - 0.5) * 2.0
    rgb = np.empty((*values.shape, 3), dtype="float32")
    rgb[lower] = stops[0] + (stops[1] - stops[0]) * ratio_low[lower, None]
    rgb[high] = stops[1] + (stops[2] - stops[1]) * ratio_high[high, None]
    for channel in range(3):
        rgba[channel][valid] = rgb[..., channel][valid].astype("uint8")
    rgba[3][valid] = 255
    return rgba


def _colourize_delta(values: np.ndarray) -> np.ndarray:
    """Display-only diverging ramp: target lower / near zero / target higher."""
    rgba = np.zeros((4, values.shape[0], values.shape[1]), dtype="uint8")
    valid = np.isfinite(values)
    normalized = np.clip((values + 1.0) / 2.0, 0.0, 1.0)
    stops = np.array([[178, 24, 43], [247, 247, 247], [33, 102, 172]], dtype="float32")
    lower = normalized <= 0.5
    rgb = np.empty((*values.shape, 3), dtype="float32")
    rgb[lower] = stops[0] + (stops[1] - stops[0]) * (normalized[lower, None] * 2.0)
    high = ~lower
    rgb[high] = stops[1] + (stops[2] - stops[1]) * (
        (normalized[high, None] - 0.5) * 2.0
    )
    for channel in range(3):
        rgba[channel][valid] = rgb[..., channel][valid].astype("uint8")
    rgba[3][valid] = 255
    return rgba


def render_ndvi_tile(
    path: str, z: int, x: int, y: int, *, delta: bool = False
) -> RasterTile:
    bounds = _tile_bounds(z, x, y)
    with rasterio.open(path) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise RasterUnavailable("derived raster is not a readable single-band COG")
        try:
            dataset_bounds = transform_bounds(dataset.crs, "EPSG:3857", *dataset.bounds)
        except Exception as exc:
            raise RasterUnavailable(
                "derived raster bounds cannot be transformed"
            ) from exc
        west, south, east, north = bounds
        if (
            east <= dataset_bounds[0]
            or west >= dataset_bounds[2]
            or north <= dataset_bounds[1]
            or south >= dataset_bounds[3]
        ):
            rgba = np.zeros((4, 256, 256), dtype="uint8")
        else:
            values = np.full((256, 256), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(dataset, 1),
                destination=values,
                src_nodata=dataset.nodata,
                dst_nodata=np.nan,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                dst_transform=from_bounds(*bounds, 256, 256),
                dst_crs="EPSG:3857",
                resampling=Resampling.bilinear,
            )
            rgba = _colourize_delta(values) if delta else _colourize(values)
    with MemoryFile() as memory:
        with memory.open(
            driver="PNG", width=256, height=256, count=4, dtype="uint8"
        ) as image:
            image.write(rgba)
        return RasterTile(memory.read(), bool(np.any(rgba[3])))
