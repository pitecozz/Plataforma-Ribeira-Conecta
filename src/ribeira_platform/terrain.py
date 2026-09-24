"""Evidence-preserving terrain calculations over an explicitly supplied DEM.

This module deliberately has no network client or provider fallback. Its caller
must persist DEM provenance before exposing results to a tenant. Terrain values
are derived context, not a survey, property-boundary assertion, or diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.mask import mask
from rasterio.transform import Affine
from shapely.geometry import LineString, shape
from shapely.ops import transform as transform_geometry


class TerrainProcessingError(ValueError):
    """The requested terrain calculation cannot be made from the supplied DEM."""


@dataclass(frozen=True)
class TerrainStatistics:
    """Summary statistics over valid, clipped DEM cells only."""

    valid_cell_count: int
    nodata_cell_count: int
    elevation_minimum_metres: float | None
    elevation_maximum_metres: float | None
    elevation_mean_metres: float | None
    slope_minimum_degrees: float | None
    slope_maximum_degrees: float | None
    slope_mean_degrees: float | None


@dataclass(frozen=True)
class TerrainProfilePoint:
    """One sampled point along a caller-supplied profile line."""

    distance_metres: float
    elevation_metres: float | None


@dataclass(frozen=True)
class TerrainAnalysis:
    """Derived terrain arrays and bounded summary for one clipped property AOI."""

    elevation_metres: np.ma.MaskedArray
    slope_degrees: np.ma.MaskedArray
    aspect_degrees_from_north: np.ma.MaskedArray  # direction of steepest descent
    hillshade: np.ma.MaskedArray
    statistics: TerrainStatistics
    limitations: tuple[str, ...]
    profile: tuple[TerrainProfilePoint, ...]


def _require_projected_metre_crs(crs: CRS | object | None) -> CRS:
    parsed = CRS.from_user_input(crs) if crs is not None else None
    if parsed is None or not parsed.is_projected:
        raise TerrainProcessingError(
            "DEM CRS must be projected before slope calculations"
        )
    units = {axis.unit_name.lower() for axis in parsed.axis_info if axis.unit_name}
    if not any("metre" in unit or "meter" in unit for unit in units):
        raise TerrainProcessingError("DEM horizontal units must be metres")
    return parsed


def _require_elevation_metres(elevation_unit: str | None) -> None:
    """Require a caller assertion before labelling DEM values as metres."""
    if not isinstance(elevation_unit, str):
        raise TerrainProcessingError("DEM elevation unit must be explicitly declared")
    normalized = elevation_unit.strip().lower()
    if normalized not in {"m", "metre", "metres", "meter", "meters"}:
        raise TerrainProcessingError(
            "terrain analysis requires DEM elevations in metres"
        )


def _transform_to_crs(geometry: dict, target_crs: CRS):
    try:
        source = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise TerrainProcessingError("geometry must be valid GeoJSON") from exc
    if source.is_empty or not source.is_valid:
        raise TerrainProcessingError("geometry must be valid and non-empty")
    if not np.isfinite(source.bounds).all():
        raise TerrainProcessingError("geometry coordinates must be finite")
    west, south, east, north = source.bounds
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise TerrainProcessingError(
            "geometry coordinates must be valid WGS84 longitude/latitude"
        )
    transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    transformed = transform_geometry(transformer.transform, source)
    if (
        transformed.is_empty
        or not transformed.is_valid
        or not np.isfinite(transformed.bounds).all()
    ):
        raise TerrainProcessingError("geometry cannot be transformed into the DEM CRS")
    return transformed


def _cell_size(transform: Affine) -> tuple[float, float]:
    if transform.b != 0 or transform.d != 0:
        raise TerrainProcessingError(
            "rotated DEM grids are not supported by terrain analysis v1"
        )
    x_size, y_size = abs(transform.a), abs(transform.e)
    if x_size <= 0 or y_size <= 0:
        raise TerrainProcessingError("DEM has invalid pixel dimensions")
    return x_size, y_size


def _derivatives(
    elevation: np.ma.MaskedArray, x_size: float, y_size: float
) -> tuple[np.ma.MaskedArray, np.ma.MaskedArray]:
    """Central differences, masking borders and incomplete neighbourhoods."""
    data = np.asarray(elevation.filled(np.nan), dtype=np.float64)
    valid = np.isfinite(data)
    dzdx = np.full(data.shape, np.nan, dtype=np.float64)
    dzdy = np.full(data.shape, np.nan, dtype=np.float64)
    if data.shape[0] >= 3 and data.shape[1] >= 3:
        neighbourhood = (
            valid[:-2, :-2]
            & valid[:-2, 1:-1]
            & valid[:-2, 2:]
            & valid[1:-1, :-2]
            & valid[1:-1, 1:-1]
            & valid[1:-1, 2:]
            & valid[2:, :-2]
            & valid[2:, 1:-1]
            & valid[2:, 2:]
        )
        dzdx[1:-1, 1:-1] = np.where(
            neighbourhood, (data[1:-1, 2:] - data[1:-1, :-2]) / (2 * x_size), np.nan
        )
        # Raster rows progress southward; this produces the northward gradient.
        dzdy[1:-1, 1:-1] = np.where(
            neighbourhood, (data[:-2, 1:-1] - data[2:, 1:-1]) / (2 * y_size), np.nan
        )
    return np.ma.masked_invalid(dzdx), np.ma.masked_invalid(dzdy)


def _profile_distances(
    line: LineString, spacing_metres: float
) -> Iterable[tuple[float, tuple[float, float]]]:
    if len(line.coords) < 2 or line.length <= 0:
        raise TerrainProcessingError(
            "terrain profile requires at least two coordinates"
        )
    if spacing_metres <= 0:
        raise TerrainProcessingError("terrain profile spacing must be positive")
    sample_count = max(1, int(np.ceil(line.length / spacing_metres)))
    for distance in np.linspace(0, line.length, num=sample_count + 1):
        point = line.interpolate(float(distance))
        yield float(distance), (float(point.x), float(point.y))


class TerrainProcessor:
    """Calculate elevation, slope, aspect, hillshade and an optional line profile."""

    algorithm_id = "TERRAIN_DERIVATIVES"
    algorithm_version = "1.1.0"
    hillshade_azimuth_degrees = 315.0
    hillshade_altitude_degrees = 45.0

    def analyze(
        self,
        dem_path: str | Path,
        aoi_geojson: dict,
        *,
        elevation_unit: str | None = None,
        profile_geojson: dict | None = None,
    ) -> TerrainAnalysis:
        _require_elevation_metres(elevation_unit)
        with rasterio.open(dem_path) as dataset:
            crs = _require_projected_metre_crs(dataset.crs)
            aoi = _transform_to_crs(aoi_geojson, crs)
            if aoi.geom_type not in {"Polygon", "MultiPolygon"}:
                raise TerrainProcessingError(
                    "terrain AOI must be a Polygon or MultiPolygon"
                )
            try:
                clipped, transform = mask(
                    dataset, [aoi.__geo_interface__], crop=True, filled=False
                )
            except ValueError as exc:
                raise TerrainProcessingError(
                    "terrain AOI does not intersect the DEM"
                ) from exc
            if clipped.shape[0] != 1:
                raise TerrainProcessingError(
                    "terrain DEM must contain exactly one elevation band"
                )
            elevation = np.ma.masked_invalid(clipped[0].astype(np.float64, copy=False))
            if elevation.count() == 0:
                raise TerrainProcessingError(
                    "terrain DEM has no valid elevation cells within the AOI"
                )
            x_size, y_size = _cell_size(transform)
            dzdx, dzdy = _derivatives(elevation, x_size, y_size)
            slope = np.ma.arctan(np.ma.sqrt(dzdx**2 + dzdy**2)) * (180.0 / np.pi)
            aspect = (np.ma.arctan2(-dzdx, -dzdy) * (180.0 / np.pi) + 360.0) % 360.0
            zenith = np.deg2rad(90.0 - self.hillshade_altitude_degrees)
            azimuth = np.deg2rad(self.hillshade_azimuth_degrees)
            hillshade = 255.0 * (
                np.cos(zenith) * np.cos((slope * np.pi / 180.0))
                + np.sin(zenith)
                * np.sin((slope * np.pi / 180.0))
                * np.cos(azimuth - (aspect * np.pi / 180.0))
            )
            profile = (
                self._profile(dataset, aoi, profile_geojson) if profile_geojson else ()
            )
        statistics = self._statistics(elevation, slope)
        limitations = (
            "Terrain values are derived from the supplied DEM, not a field survey or legal boundary.",
            "Slope, aspect and hillshade require complete 3x3 elevation neighbourhoods; edges and nodata remain unavailable.",
            f"Hillshade uses azimuth {self.hillshade_azimuth_degrees:.0f}° and altitude {self.hillshade_altitude_degrees:.0f}°.",
        )
        return TerrainAnalysis(
            elevation,
            slope,
            aspect,
            np.ma.clip(hillshade, 0, 255),
            statistics,
            limitations,
            tuple(profile),
        )

    @staticmethod
    def _statistics(
        elevation: np.ma.MaskedArray, slope: np.ma.MaskedArray
    ) -> TerrainStatistics:
        valid, valid_slope = elevation.compressed(), slope.compressed()
        return TerrainStatistics(
            valid_cell_count=int(valid.size),
            nodata_cell_count=int(np.ma.getmaskarray(elevation).sum()),
            elevation_minimum_metres=float(valid.min()) if valid.size else None,
            elevation_maximum_metres=float(valid.max()) if valid.size else None,
            elevation_mean_metres=float(valid.mean()) if valid.size else None,
            slope_minimum_degrees=float(valid_slope.min())
            if valid_slope.size
            else None,
            slope_maximum_degrees=float(valid_slope.max())
            if valid_slope.size
            else None,
            slope_mean_degrees=float(valid_slope.mean()) if valid_slope.size else None,
        )

    @staticmethod
    def _profile(
        dataset: rasterio.DatasetReader, aoi, profile_geojson: dict
    ) -> list[TerrainProfilePoint]:
        line = _transform_to_crs(
            profile_geojson, _require_projected_metre_crs(dataset.crs)
        )
        if not isinstance(line, LineString):
            raise TerrainProcessingError("terrain profile must be a LineString")
        if not aoi.covers(line):
            raise TerrainProcessingError(
                "terrain profile must be fully contained by the terrain AOI"
            )
        points = list(_profile_distances(line, min(_cell_size(dataset.transform))))
        samples = dataset.sample([coordinate for _, coordinate in points], masked=True)
        return [
            TerrainProfilePoint(
                distance,
                None
                if np.ma.is_masked(sample[0]) or not np.isfinite(sample[0])
                else float(sample[0]),
            )
            for (distance, _), sample in zip(points, samples, strict=True)
        ]
