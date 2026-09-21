"""Conservative Sentinel-1 metadata selection for factual event evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .time_utils import parse_aware


@dataclass(frozen=True)
class Sentinel1SceneCandidate:
    provider_record_id: str
    acquired_at: datetime
    mode: str
    orbit_state: str
    relative_orbit: int
    polarizations: tuple[str, ...]
    geometry: dict[str, Any]
    metadata: dict[str, Any]

    @property
    def comparability_key(self) -> tuple[str, str, int, tuple[str, ...]]:
        return self.mode, self.orbit_state, self.relative_orbit, self.polarizations


def parse_sentinel1_grd_item(item: dict[str, Any]) -> Sentinel1SceneCandidate:
    properties = item.get("properties")
    geometry = item.get("geometry")
    record_id = item.get("id")
    if (
        not isinstance(properties, dict)
        or not isinstance(geometry, dict)
        or not isinstance(record_id, str)
    ):
        raise ValueError("Sentinel-1 STAC item is missing required metadata")
    acquired = properties.get("datetime")
    mode = properties.get("sar:instrument_mode")
    orbit_state = properties.get("sat:orbit_state")
    relative_orbit = properties.get("sat:relative_orbit")
    polarizations = properties.get("sar:polarizations")
    if (
        not isinstance(acquired, str)
        or not isinstance(mode, str)
        or not isinstance(orbit_state, str)
    ):
        raise ValueError("Sentinel-1 STAC item has incomplete acquisition metadata")
    if (
        not isinstance(relative_orbit, int)
        or not isinstance(polarizations, list)
        or not all(isinstance(value, str) for value in polarizations)
    ):
        raise ValueError(
            "Sentinel-1 STAC item has invalid orbit or polarization metadata"
        )
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Sentinel-1 STAC item has invalid geometry")
    return Sentinel1SceneCandidate(
        provider_record_id=record_id,
        acquired_at=parse_aware(acquired),
        mode=mode,
        orbit_state=orbit_state,
        relative_orbit=relative_orbit,
        polarizations=tuple(sorted(polarizations)),
        geometry=geometry,
        metadata={
            "instrument_mode": mode,
            "orbit_state": orbit_state,
            "relative_orbit": relative_orbit,
            "polarizations": sorted(polarizations),
            "product_type": properties.get("sar:product_type"),
        },
    )


def select_comparable_pair(
    items: list[dict[str, Any]], *, event_start: datetime, event_end: datetime
) -> tuple[Sentinel1SceneCandidate, Sentinel1SceneCandidate] | None:
    """Choose the nearest pre-event and event/post-event pair with matching SAR geometry."""
    candidates = [parse_sentinel1_grd_item(item) for item in items]
    pre = [candidate for candidate in candidates if candidate.acquired_at < event_start]
    event = [
        candidate
        for candidate in candidates
        if event_start <= candidate.acquired_at <= event_end
    ]
    pairs = [
        (before, after)
        for before in pre
        for after in event
        if before.comparability_key == after.comparability_key
    ]
    if not pairs:
        return None
    return min(
        pairs,
        key=lambda pair: (
            (event_start - pair[0].acquired_at).total_seconds(),
            (pair[1].acquired_at - event_start).total_seconds(),
        ),
    )
