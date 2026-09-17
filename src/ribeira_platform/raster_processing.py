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
from rasterio.windows import Window
from rasterio.warp import reproject, transform_geom
from shapely.geometry import shape

from .geospatial import BandResolver, GeospatialQuality, NdviStatistics, SatelliteAsset
from .object_storage import LocalObjectStorage, ObjectStorageError
from .sentinel2_quality import Sentinel2QualityPolicy


class RasterProcessingError(RuntimeError):
    def __init__(self, quality: GeospatialQuality, message: str) -> None:
        super().__init__(message)
        self.quality = quality


def validate_cog(
    path: str | Path,
    *,
    expected_crs: Any | None = None,
    expected_transform: Any | None = None,
    expected_shape: tuple[int, int] | None = None,
    expected_value_range: tuple[float, float] | None = (-1.0, 1.0),
) -> None:
    """Validate the structural and semantic properties of a derived NDVI COG.

    ``IMAGE_STRUCTURE:LAYOUT=COG`` is GDAL's recognition of the internal COG
    organization.  The additional checks protect the raster contract that the
    downstream product record describes, rather than trusting a file suffix or
    a creation option alone.
    """
    with rasterio.open(path) as dataset:
        layout = dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT")
        if dataset.driver != "GTiff" or layout != "COG":
            raise ValueError("GeoTIFF is not recognized by GDAL as a COG")
        if dataset.count != 1:
            raise ValueError("derived COG must contain one NDVI band")
        if not dataset.block_shapes or any(
            block_height <= 1 or block_width <= 1
            for block_height, block_width in dataset.block_shapes
        ):
            raise ValueError("derived COG must use tiled internal blocks")
        if dataset.compression is None or dataset.compression.value != "DEFLATE":
            raise ValueError("derived COG must use DEFLATE compression")
        if dataset.crs is None:
            raise ValueError("derived COG requires a CRS")
        if expected_crs is not None and dataset.crs != expected_crs:
            raise ValueError("derived COG CRS differs from the RED input")
        if expected_transform is not None and dataset.transform != expected_transform:
            raise ValueError("derived COG transform differs from the RED input")
        if (
            expected_shape is not None
            and (dataset.height, dataset.width) != expected_shape
        ):
            raise ValueError("derived COG dimensions differ from the NDVI window")
        if dataset.nodata is None or not np.isnan(dataset.nodata):
            raise ValueError("derived COG must use NaN nodata")

        # Read a real window from the persisted object.  This catches a broken
        # TIFF directory or unusable tile independently of writer-side arrays.
        window = Window(
            0,
            0,
            min(dataset.width, 64),
            min(dataset.height, 64),
        )
        values = dataset.read(1, window=window, masked=True)
        valid = values.compressed()
        if expected_value_range is not None and valid.size and (
            bool(np.any(valid < expected_value_range[0]))
            or bool(np.any(valid > expected_value_range[1]))
        ):
            raise ValueError("derived COG window contains values outside its expected range")


@dataclass(frozen=True)
class RasterProcessingOutput:
    statistics: NdviStatistics
    output_reference: str
    output_checksum: str
    input_asset_keys: list[str]
    limitations: list[str]
    quality: list[GeospatialQuality]
    quality_mask: dict[str, Any] | None = None


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
        quality_policy: Sentinel2QualityPolicy | None = None,
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
            scl_path = (
                self.object_storage.read_local_path(asset_map[quality_policy.scl_asset_key].href)
                if quality_policy is not None
                else None
            )
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
                mask_record = None
                if quality_policy is not None:
                    if scl_path is None:
                        raise RasterProcessingError(GeospatialQuality.ASSET_UNAVAILABLE, "SCL asset is unavailable")
                    with rasterio.open(scl_path) as scl_ds:
                        scl = self._read_aligned(scl_ds, red_ds, aoi_geojson, red.shape[1:], transform)
                    scl_values = scl[0]
                    scl_valid = ~np.ma.getmaskarray(scl[0]) & np.isfinite(scl_values)
                    accepted = quality_policy.accepts(scl_values)
                    valid_before_scl = int(valid.sum())
                    valid &= scl_valid & accepted
                    mask_record = {
                        **quality_policy.record(),
                        "valid_before_scl": valid_before_scl,
                        "discarded_by_scl": valid_before_scl - int(valid.sum()),
                        "valid_after_scl": int(valid.sum()),
                    }
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
                if bool(np.any(valid_values < -1.0)) or bool(
                    np.any(valid_values > 1.0)
                ):
                    raise RasterProcessingError(
                        GeospatialQuality.NDVI_OUT_OF_RANGE,
                        "NDVI contains values outside the theoretical range [-1, 1]",
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
                    [roles["red"], roles["nir"]] + ([quality_policy.scl_asset_key] if quality_policy else []),
                    limitations,
                    quality,
                    mask_record,
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
        source_values = source.data.astype("float32", copy=True)
        source_values[np.ma.getmaskarray(source)] = np.nan
        reproject(
            source=source_values,
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
        expected_value_range: tuple[float, float] | None = (-1.0, 1.0),
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
        output_reference, checksum = self.object_storage.put_bytes(
            output_key, payload, "image/tiff"
        )
        local_path = self.object_storage.read_local_path(output_reference)
        try:
            validate_cog(
                local_path,
                expected_crs=reference.crs,
                expected_transform=transform,
                expected_shape=values.shape,
                expected_value_range=expected_value_range,
            )
        except (ValueError, rasterio.errors.RasterioIOError) as exc:
            raise RasterProcessingError(
                GeospatialQuality.PROCESSING_FAILED,
                f"derived raster failed COG validation: {exc}",
            ) from exc
        return output_reference, checksum


@dataclass(frozen=True)
class DeltaRasterProcessingOutput:
    statistics: NdviStatistics
    output_reference: str
    output_checksum: str
    alignment: dict[str, Any]


class TemporalDeltaProcessor:
    algorithm_id = "NDVI_TEMPORAL_DELTA"
    algorithm_version = "1.0.0"
    formula = "NDVI_target - NDVI_baseline"

    def __init__(self, object_storage: LocalObjectStorage) -> None:
        self.object_storage = object_storage

    def process(self, baseline_reference: str, target_reference: str, output_key: str) -> DeltaRasterProcessingOutput:
        baseline_path = self.object_storage.read_local_path(baseline_reference)
        target_path = self.object_storage.read_local_path(target_reference)
        with rasterio.open(baseline_path) as baseline, rasterio.open(target_path) as target:
            baseline_values = baseline.read(1).astype("float32")
            same_grid = (
                baseline.crs == target.crs
                and baseline.transform == target.transform
                and baseline.width == target.width
                and baseline.height == target.height
            )
            if same_grid:
                target_values = target.read(1).astype("float32")
                alignment: dict[str, Any] = {"status": "IDENTICAL_GRID", "target_grid": "baseline", "resampling": None}
            else:
                target_values = np.full(baseline_values.shape, np.nan, dtype="float32")
                reproject(
                    source=rasterio.band(target, 1), destination=target_values,
                    src_transform=target.transform, src_crs=target.crs,
                    dst_transform=baseline.transform, dst_crs=baseline.crs,
                    src_nodata=target.nodata, dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
                alignment = {"status": "ALIGNED_TO_BASELINE_GRID", "target_grid": "baseline", "resampling": "bilinear"}
            comparable = np.isfinite(baseline_values) & np.isfinite(target_values)
            values = np.full(baseline_values.shape, np.nan, dtype="float32")
            values[comparable] = target_values[comparable] - baseline_values[comparable]
            valid_values = values[np.isfinite(values)]
            total = int(values.size)
            if valid_values.size == 0:
                raise RasterProcessingError(GeospatialQuality.PROCESSING_FAILED, "quality-masked NDVI products have no comparable pixels")
            stats = NdviStatistics(
                int(valid_values.size), total - int(valid_values.size),
                Decimal(str(float(valid_values.min()))), Decimal(str(float(valid_values.max()))),
                Decimal(str(float(valid_values.mean()))), Decimal(str(float(np.median(valid_values))),),
                Decimal(str(round(valid_values.size / total * 100, 6))),
            )
            output, checksum = NdviProcessor(self.object_storage)._write_cog(
                values, baseline, baseline.transform, output_key, expected_value_range=(-2.0, 2.0)
            )
        alignment.update({"reference_pixels": total, "baseline_valid_pixels": int(np.isfinite(baseline_values).sum()), "target_valid_pixels": int(np.isfinite(target_values).sum()), "comparable_valid_pixels": stats.valid_count})
        return DeltaRasterProcessingOutput(stats, output, checksum, alignment)


def algorithm_parameters(aoi_geojson: dict[str, Any]) -> dict[str, Any]:
    return {
        "aoi_checksum": hashlib.sha256(
            json.dumps(aoi_geojson, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "nodata_policy": "NO_DATA",
        "resampling": "nearest",
    }
