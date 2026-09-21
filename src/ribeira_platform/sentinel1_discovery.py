"""Exact-footprint, catalogue-only Sentinel-1 pair discovery for Registro."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from .sentinel1 import Sentinel1SceneCandidate, parse_sentinel1_grd_item


METRIC_CRS = "EPSG:32723"
SOURCE_CRS = "EPSG:4674"


@dataclass(frozen=True)
class EventWindow:
    start: datetime
    end: datetime
    evidence: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class SceneAssessment:
    scene: Sentinel1SceneCandidate
    platform: str | None
    product_type: str | None
    absolute_orbit: int | None
    coverage_km2: float
    coverage_percent: float
    pre_classification: str
    pre_reason: str
    event_classification: str
    event_reason: str


@dataclass(frozen=True)
class PairAssessment:
    pre: SceneAssessment
    event: SceneAssessment
    common_geometry: dict[str, Any]
    common_coverage_km2: float
    common_coverage_percent: float
    pre_to_event_days: float
    event_offset_days: float
    rank_order: int | None = None


def derive_event_window(entries: Iterable[dict[str, Any]]) -> EventWindow:
    """Derive a bounded event interval only from persisted factual evidence.

    A reservoir-operation or rainfall-peak entry starts the window. An official
    Registro report (stored as EVENT_PRIORITY) or the last peak ends it. Climate
    entries are deliberately ignored: they are context, not an event marker.
    """
    factual = [
        item
        for item in entries
        if item.get("event_type")
        in {"RESERVOIR_OPERATION", "RAINFALL_ACCUMULATION_PEAK", "EVENT_PRIORITY"}
        and isinstance(item.get("occurred_at"), datetime)
    ]
    starts = [
        item["occurred_at"]
        for item in factual
        if item["event_type"] in {"RESERVOIR_OPERATION", "RAINFALL_ACCUMULATION_PEAK"}
    ]
    ends = [
        item["occurred_at"]
        for item in factual
        if item["event_type"] == "EVENT_PRIORITY"
    ]
    peaks = [
        item["occurred_at"]
        for item in factual
        if item["event_type"] == "RAINFALL_ACCUMULATION_PEAK"
    ]
    if not starts or not (ends or peaks):
        raise ValueError("persisted factual evidence cannot define an event window")
    return EventWindow(
        start=min(starts), end=max(ends + peaks), evidence=tuple(factual)
    )


def search_window(event_window: EventWindow) -> tuple[datetime, datetime]:
    """Use a 28-day pre-search and a bounded ten-day post-event allowance."""
    return event_window.start - timedelta(days=28), event_window.end + timedelta(
        days=10
    )


def _project(geometry: dict[str, Any]):  # type: ignore[no-untyped-def]
    geom = shape(geometry)
    if geom.is_empty or not geom.is_valid:
        raise ValueError("geometry must be valid and non-empty")
    transformer = Transformer.from_crs(SOURCE_CRS, METRIC_CRS, always_xy=True).transform
    return transform(transformer, geom)


def assess_scene(
    item: dict[str, Any], registro_geometry: dict[str, Any], event_window: EventWindow
) -> SceneAssessment:
    candidate = parse_sentinel1_grd_item(item)
    registro = _project(registro_geometry)
    footprint = _project(candidate.geometry)
    intersection = registro.intersection(footprint)
    coverage_km2 = intersection.area / 1_000_000
    coverage_percent = coverage_km2 / (registro.area / 1_000_000) * 100
    properties = item["properties"]
    platform = (
        properties.get("platform")
        if isinstance(properties.get("platform"), str)
        else None
    )
    product_type = properties.get("product:type")
    absolute_orbit = properties.get("sat:absolute_orbit")
    if not isinstance(product_type, str):
        product_type = None
    if not isinstance(absolute_orbit, int):
        absolute_orbit = None
    if coverage_km2 <= 0:
        pre, pre_reason = "REJECTED", "exact Registro-footprint intersection is zero"
        event, event_reason = pre, pre_reason
    elif candidate.mode.upper() != "IW" or not {"VV", "VH"}.issubset(
        candidate.polarizations
    ):
        pre, pre_reason = "REJECTED", "not IW dual-polarization VV/VH GRD"
        event, event_reason = pre, pre_reason
    elif candidate.acquired_at < event_window.start:
        age_days = (event_window.start - candidate.acquired_at).total_seconds() / 86400
        pre = (
            "GOOD_PRE"
            if age_days <= 10
            else "POSSIBLE_PRE"
            if age_days <= 28
            else "POOR_PRE"
        )
        pre_reason = f"{age_days:.1f} days before first persisted factual event signal"
        event, event_reason = "NOT_APPLICABLE", "acquired before factual event window"
    elif candidate.acquired_at <= event_window.end:
        pre, pre_reason = "REJECTED", "acquired during factual event window"
        event, event_reason = "GOOD_EVENT", "acquired during factual event window"
    else:
        offset_days = (candidate.acquired_at - event_window.end).total_seconds() / 86400
        pre, pre_reason = "REJECTED", "acquired after factual event window"
        event = "POSSIBLE_EVENT" if offset_days <= 10 else "POOR_EVENT"
        event_reason = f"{offset_days:.1f} days after factual event window"
    return SceneAssessment(
        scene=candidate,
        platform=platform,
        product_type=product_type,
        absolute_orbit=absolute_orbit,
        coverage_km2=coverage_km2,
        coverage_percent=coverage_percent,
        pre_classification=pre,
        pre_reason=pre_reason,
        event_classification=event,
        event_reason=event_reason,
    )


def compatible(left: SceneAssessment, right: SceneAssessment) -> bool:
    return (
        left.scene.comparability_key == right.scene.comparability_key
        and left.product_type == right.product_type
        and left.coverage_km2 > 0
        and right.coverage_km2 > 0
    )


def build_pairs(
    scenes: Iterable[SceneAssessment],
    registro_geometry: dict[str, Any],
    event_window: EventWindow,
) -> list[PairAssessment]:
    registro = _project(registro_geometry)
    pre = [
        item
        for item in scenes
        if item.pre_classification in {"GOOD_PRE", "POSSIBLE_PRE", "POOR_PRE"}
    ]
    event = [
        item
        for item in scenes
        if item.event_classification in {"GOOD_EVENT", "POSSIBLE_EVENT", "POOR_EVENT"}
    ]
    pairs: list[PairAssessment] = []
    for before in pre:
        for after in event:
            if not compatible(before, after):
                continue
            common = registro.intersection(
                _project(before.scene.geometry)
            ).intersection(_project(after.scene.geometry))
            area = common.area / 1_000_000
            if area <= 0:
                continue
            pairs.append(
                PairAssessment(
                    pre=before,
                    event=after,
                    common_geometry=mapping(
                        transform(
                            Transformer.from_crs(
                                METRIC_CRS, SOURCE_CRS, always_xy=True
                            ).transform,
                            common,
                        )
                    ),
                    common_coverage_km2=area,
                    common_coverage_percent=area / (registro.area / 1_000_000) * 100,
                    pre_to_event_days=(
                        after.scene.acquired_at - before.scene.acquired_at
                    ).total_seconds()
                    / 86400,
                    event_offset_days=(
                        after.scene.acquired_at - event_window.start
                    ).total_seconds()
                    / 86400,
                )
            )
    return rank_pairs(pairs)


def rank_pairs(pairs: Iterable[PairAssessment]) -> list[PairAssessment]:
    """Transparent ordered ranking: coverage, compatibility, timing, interval, pol."""
    pre_rank = {"GOOD_PRE": 0, "POSSIBLE_PRE": 1, "POOR_PRE": 2}
    event_rank = {"GOOD_EVENT": 0, "POSSIBLE_EVENT": 1, "POOR_EVENT": 2}
    ranked = sorted(
        pairs,
        key=lambda pair: (
            -pair.common_coverage_km2,
            event_rank[pair.event.event_classification],
            pre_rank[pair.pre.pre_classification],
            pair.pre_to_event_days,
            0 if {"VV", "VH"}.issubset(pair.pre.scene.polarizations) else 1,
        ),
    )
    return [
        PairAssessment(**{**pair.__dict__, "rank_order": index})
        for index, pair in enumerate(ranked, start=1)
    ]


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("factual timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)
