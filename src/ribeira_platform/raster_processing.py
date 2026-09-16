from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.mask import mask
from rasterio.warp import reproject, transform_geom
from shapely.geometry import shape

from .geospatial import BandResolver, GeospatialQuality, NdviStatistics, SatelliteAsset
from .object_storage import LocalObjectStorage, ObjectStorageError


class RasterProcessingError(RuntimeError):
    def __init__(self, quality: GeospatialQuality, message: str) -> None:
        super().__init__(message)
        self.quality = quality


@dataclass(frozen=True)
class RasterProcessingOutput:
    statistics: NdviStatistics
    output_reference: str
    output_checksum: str
    input_asset_keys: list[str]
    limitations: list[str]
    quality: list[GeospatialQuality]


class NdviProcessor:
    algorithm_id = "NDVI"
    algorithm_version = "1.0.0"
    formula = "(NIR - RED) / (NIR + RED)"

    def __init__(self, object_storage: LocalObjectStorage) -> None:
        self.object_storage = object_storage

    def process(
        self,
        assets: list[SatelliteAsset],
        aoi_geojson: dict[str, Any],
        output_key: str,
    ) -> RasterProcessingOutput:
        asset_map = {item.asset_key: item for item in assets}
        try:
            roles = BandResolver.resolve(
                {
                    item.asset_key: {
                        "title": item.title,
                        "roles": item.roles,
                    }
                    for item in assets
                }
            )
        except ValueError as exc:
            raise RasterProcessingError(
                GeospatialQuality.ASSET_UNAVAILABLE,
                str(exc),
            ) from exc
        try:
            red_path = self.object_storage.read_local_path(asset_map[roles["red"]].href)
            nir_path = self.object_storage.read_local_path(asset_map[roles["nir"]].href)
        except (KeyError, ObjectStorageError) as exc:
            raise RasterProcessingError(
                GeospatialQuality.ASSET_UNAVAILABLE,
                "validated red/NIR assets are not available to the local processor",
            ) from exc
        try:
            with rasterio.open(red_path) as red_ds, rasterio.open(nir_path) as nir_ds:
                red, transform = self._crop(red_ds, aoi_geojson)
                nir = self._read_aligned(
                    nir_ds, red_ds, aoi_geojson, red.shape[1:], transform
                )
                red_values = red[0].astype("float32")
                nir_values = nir[0].astype("float32")
                red_mask = np.ma.getmaskarray(red[0])
                nir_mask = np.ma.getmaskarray(nir[0])
                denominator = nir_values + red_values
                valid = (
                    ~(red_mask | nir_mask)
                    & np.isfinite(denominator)
                    & (denominator != 0)
                )
                ndvi = np.full(red_values.shape, np.nan, dtype="float32")
                ndvi[valid] = (nir_values[valid] - red_values[valid]) / denominator[
                    valid
                ]
                valid_values = ndvi[np.isfinite(ndvi)]
                total = int(ndvi.size)
                valid_count = int(valid_values.size)
                nodata_count = total - valid_count
                if valid_count == 0:
                    raise RasterProcessingError(
                        GeospatialQuality.PROCESSING_FAILED,
                        "NDVI window contains no valid pixels",
                    )
                stats = NdviStatistics(
                    valid_count=valid_count,
                    nodata_count=nodata_count,
                    minimum=Decimal(str(float(valid_values.min()))),
                    maximum=Decimal(str(float(valid_values.max()))),
                    mean=Decimal(str(float(valid_values.mean()))),
                    median=Decimal(str(float(np.median(valid_values)))),
                    coverage_percentage=Decimal(
                        str(round(valid_count / total * 100, 6))
                    ),
                )
                output = self._write_cog(ndvi, red_ds, transform, output_key)
                limitations: list[str] = []
                quality: list[GeospatialQuality] = []
                if (
                    stats.coverage_percentage is not None
                    and stats.coverage_percentage < 100
                ):
                    quality.append(GeospatialQuality.PARTIAL_COVERAGE)
                    limitations.append(
                        "NDVI statistics cover only valid pixels inside the AOI"
                    )
                return RasterProcessingOutput(
                    stats,
                    output[0],
                    output[1],
                    [roles["red"], roles["nir"]],
                    limitations,
                    quality,
                )
        except RasterProcessingError:
            raise
        except (OSError, rasterio.errors.RasterioIOError, ValueError) as exc:
            raise RasterProcessingError(
                GeospatialQuality.PROCESSING_FAILED,
                f"raster processing failed: {type(exc).__name__}",
            ) from exc

    @staticmethod
    def _crop(dataset: rasterio.DatasetReader, aoi_geojson: dict[str, Any]):
        geometry = shape(aoi_geojson)
        if dataset.crs is None:
            raise ValueError("input raster CRS is required")
        if dataset.crs.to_string() != "EPSG:4326":
            geometry = shape(
                transform_geom("EPSG:4326", dataset.crs, geometry.__geo_interface__)
            )
        return mask(dataset, [geometry], crop=True, filled=False)

    @staticmethod
    def _read_aligned(
        dataset: rasterio.DatasetReader,
        reference: rasterio.DatasetReader,
        aoi_geojson: dict[str, Any],
        shape_: tuple[int, int],
        transform,
    ):
        geometry = shape(aoi_geojson)
        if dataset.crs is None or reference.crs is None:
            raise ValueError("input rasters CRS is required")
        if dataset.crs.to_string() != "EPSG:4326":
            geometry = shape(
                transform_geom("EPSG:4326", dataset.crs, geometry.__geo_interface__)
            )
        source, source_transform = mask(dataset, [geometry], crop=True, filled=False)
        if (
            dataset.crs == reference.crs
            and source.shape[1:] == shape_
            and source_transform == transform
        ):
            return source
        destination = np.ma.masked_all((1, shape_[0], shape_[1]), dtype="float32")
        reproject(
            source=source.filled(np.nan),
            destination=destination.data,
            src_transform=source_transform,
            src_crs=dataset.crs,
            dst_transform=transform,
            dst_crs=reference.crs,
            resampling=Resampling.nearest,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
        destination.mask = ~np.isfinite(destination.data)
        return destination

    def _write_cog(
        self,
        values: np.ndarray,
        reference: rasterio.DatasetReader,
        transform,
        output_key: str,
    ) -> tuple[str, str]:
        with tempfile.NamedTemporaryFile(suffix=".tif") as temporary:
            with rasterio.open(
                temporary.name,
                "w",
                driver="COG",
                height=values.shape[0],
                width=values.shape[1],
                count=1,
                dtype="float32",
                crs=reference.crs,
                transform=transform,
                nodata=np.nan,
                compress="deflate",
                BIGTIFF="IF_SAFER",
            ) as output:
                output.write(values, 1)
            payload = Path(temporary.name).read_bytes()
        reference, checksum = self.object_storage.put_bytes(
            output_key, payload, "image/tiff"
        )
        local_path = self.object_storage.read_local_path(reference)
        with rasterio.open(local_path) as check:
            if (
                check.driver not in {"COG", "GTiff"}
                or check.count != 1
                or check.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG"
            ):
                raise RasterProcessingError(
                    GeospatialQuality.PROCESSING_FAILED,
                    "derived raster failed COG validation",
                )
        return reference, checksum


def algorithm_parameters(aoi_geojson: dict[str, Any]) -> dict[str, Any]:
    return {
        "aoi_checksum": hashlib.sha256(
            json.dumps(aoi_geojson, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "nodata_policy": "NO_DATA",
        "resampling": "nearest",
    }
