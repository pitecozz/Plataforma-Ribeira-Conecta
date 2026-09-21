"""Evidence-first global hydrology primitives for Phase 1P.1.

This module intentionally does not turn unavailable providers into estimates.
It contains no tenant data: tenant exposure and decisions are a later layer.
"""

from __future__ import annotations

import html
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol, Sequence


class HydroFetchStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY_VALID_RESULT = "EMPTY_VALID_RESULT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PARSE_ERROR = "PARSE_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    STALE = "STALE"


class HydroVariable(StrEnum):
    RAINFALL = "RAINFALL"
    RIVER_STAGE = "RIVER_STAGE"
    DISCHARGE = "DISCHARGE"


@dataclass(frozen=True)
class HydroFetchResult:
    status: HydroFetchStatus
    items: tuple[object, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class HydroStationInput:
    provider: str
    provider_station_id: str
    name: str
    station_type: str
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class HydroObservationInput:
    station_id: str | None
    provider: str
    variable: HydroVariable
    observed_at: datetime
    value: float
    unit: str
    quality_flag: str = "VALID"
    classification: str = "OFFICIAL_SOURCE"
    raw_reference: str | None = None


@dataclass(frozen=True)
class CopelOperationEvent:
    reservoir_provider_id: str
    reservoir_name: str
    river_name: str | None
    event_type: str
    published_at: datetime
    effective_at: datetime | None
    numeric_value: float | None
    unit: str | None
    description_sanitized: str
    source_reference: str
    classification: str = "OFFICIAL_SOURCE"


@dataclass(frozen=True)
class EnsoContext:
    provider: str
    issued_on: date
    valid_window: str | None
    enso_state: str
    probability: float | None
    strength_category: str | None
    source_reference: str
    classification: str = "OFFICIAL_SOURCE"


class HydrologySourceAdapter(Protocol):
    def list_stations(self) -> HydroFetchResult: ...

    def fetch_observations(self) -> HydroFetchResult: ...

    def health_check(self) -> HydroFetchResult: ...


_UNITS: dict[HydroVariable, frozenset[str]] = {
    HydroVariable.RAINFALL: frozenset({"mm"}),
    HydroVariable.RIVER_STAGE: frozenset({"m", "cm"}),
    HydroVariable.DISCHARGE: frozenset({"m3/s", "m³/s", "L/s"}),
}


def station_quality_issues(station: HydroStationInput) -> frozenset[str]:
    issues: set[str] = set()
    if not station.provider or not station.provider_station_id or not station.name:
        issues.add("MISSING_STATION")
    if (station.latitude is None) != (station.longitude is None):
        issues.add("INVALID_COORDINATE")
    elif station.latitude is not None and station.longitude is not None:
        if not (-90 <= station.latitude <= 90 and -180 <= station.longitude <= 180):
            issues.add("INVALID_COORDINATE")
    return frozenset(issues)


def observation_quality_issues(
    observation: HydroObservationInput,
    *,
    now: datetime | None = None,
    stale_after: timedelta | None = None,
    conflicting_provider: bool = False,
) -> frozenset[str]:
    """Report quality markers without changing a provider's original value."""
    now = now or datetime.now(timezone.utc)
    issues: set[str] = set()
    if not observation.station_id:
        issues.add("MISSING_STATION")
    if not math.isfinite(observation.value):
        issues.add("INVALID_NUMERIC_VALUE")
    if observation.unit not in _UNITS[observation.variable]:
        issues.add("UNSUPPORTED_UNIT")
    if observation.observed_at.tzinfo is None:
        issues.add("INVALID_TIMESTAMP")
    else:
        observed = observation.observed_at.astimezone(timezone.utc)
        if observed > now.astimezone(timezone.utc):
            issues.add("FUTURE_TIMESTAMP")
        if (
            stale_after is not None
            and observed < now.astimezone(timezone.utc) - stale_after
        ):
            issues.add("STALE_OBSERVATION")
    if observation.variable == HydroVariable.RAINFALL and observation.value < 0:
        issues.add("NEGATIVE_RAINFALL")
    if conflicting_provider:
        issues.add("PROVIDER_CONFLICT")
    return frozenset(issues)


def observation_deduplication_key(
    observation: HydroObservationInput,
) -> tuple[str, str, datetime, str]:
    if not observation.station_id:
        raise ValueError("station id is required for deterministic deduplication")
    if observation.observed_at.tzinfo is None:
        raise ValueError("timezone-aware observation timestamp required")
    return (
        observation.station_id,
        observation.variable.value,
        observation.observed_at.astimezone(timezone.utc),
        observation.provider,
    )


def rainfall_accumulations(
    samples: Sequence[HydroObservationInput], *, end_at: datetime
) -> dict[int, float | None]:
    """Sum raw millimetre observations by exact rolling window; missing stays null."""
    if end_at.tzinfo is None:
        raise ValueError("timezone-aware end timestamp required")
    end = end_at.astimezone(timezone.utc)
    rainfall = [
        item
        for item in samples
        if item.variable == HydroVariable.RAINFALL
        and item.unit == "mm"
        and not observation_quality_issues(item, now=end)
    ]
    result: dict[int, float | None] = {}
    for hours in (1, 3, 6, 12, 24, 48, 72, 120):
        start = end - timedelta(hours=hours)
        values = [
            item.value
            for item in rainfall
            if start < item.observed_at.astimezone(timezone.utc) <= end
        ]
        result[hours] = sum(values) if values else None
    return result


def river_stage_deltas(
    samples: Sequence[HydroObservationInput], *, end_at: datetime
) -> dict[str, float | None]:
    """Calculate only from exact timestamps, never interpolating missing stage."""
    if end_at.tzinfo is None:
        raise ValueError("timezone-aware end timestamp required")
    end = end_at.astimezone(timezone.utc)
    values = {
        item.observed_at.astimezone(timezone.utc): item.value
        for item in samples
        if item.variable == HydroVariable.RIVER_STAGE
        and item.unit == "m"
        and not observation_quality_issues(item, now=end)
    }
    result: dict[str, float | None] = {}
    for label, delta in (
        ("15m", timedelta(minutes=15)),
        ("30m", timedelta(minutes=30)),
        ("1h", timedelta(hours=1)),
        ("3h", timedelta(hours=3)),
        ("6h", timedelta(hours=6)),
        ("12h", timedelta(hours=12)),
        ("24h", timedelta(hours=24)),
    ):
        before = end - delta
        result[label] = (
            values[end] - values[before] if end in values and before in values else None
        )
    return result


def rate_of_rise(delta: float | None, elapsed: timedelta) -> float | None:
    if delta is None or elapsed.total_seconds() <= 0:
        return None
    return delta / elapsed.total_seconds()


class AnaHidroWebAdapter:
    """Structural modern ANA HidroWebService adapter; OAuth is intentionally external."""

    config_path = Path.home() / ".config/ribeira/ana-hidroweb.env"
    inventory_endpoint = "/Estacoes/Inventario"
    telemetry_endpoints = {
        HydroVariable.RAINFALL: "/Estacoes/Telemetricas/Chuva",
        HydroVariable.RIVER_STAGE: "/Estacoes/Telemetricas/Cota",
        HydroVariable.DISCHARGE: "/Estacoes/Telemetricas/Vazao",
    }

    def _auth_state(self) -> HydroFetchResult:
        # Presence alone is not treated as authorization.  The private file is
        # read only by a future credential-aware client, never by this probe.
        return HydroFetchResult(
            HydroFetchStatus.AUTH_REQUIRED,
            detail="official ANA OAuth credentials are required",
        )

    def list_stations(self) -> HydroFetchResult:
        return self._auth_state()

    def fetch_observations(self) -> HydroFetchResult:
        return self._auth_state()

    def health_check(self) -> HydroFetchResult:
        return self._auth_state()


class SaispPublicAdapter:
    """SAISP remains a manual evidence source until a stable public contract exists."""

    def list_stations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.SOURCE_UNAVAILABLE,
            detail="public automation contract not verified",
        )

    def fetch_observations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.SOURCE_UNAVAILABLE,
            detail="public automation contract not verified",
        )

    def health_check(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.SOURCE_UNAVAILABLE,
            detail="public automation contract not verified",
        )


class CemadenPedAdapter:
    """CEMADEN PED is catalogued but never probed without its official JWT."""

    def list_stations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.AUTH_REQUIRED, detail="CEMADEN PED JWT is required"
        )

    def fetch_observations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.AUTH_REQUIRED, detail="CEMADEN PED JWT is required"
        )

    def health_check(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.AUTH_REQUIRED, detail="CEMADEN PED JWT is required"
        )


def _fetch_text(
    url: str, *, timeout_seconds: float = 10.0, max_bytes: int = 1_000_000
) -> str:
    request = urllib.request.Request(
        url, headers={"Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 -- fixed official URLs below
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("provider response exceeds size limit")
    return payload.decode("utf-8", errors="replace")


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def parse_copel_capivari_notice(
    html_document: str, source_reference: str
) -> CopelOperationEvent:
    """Accept only the explicit Capivari gate-opening fact from an official notice."""
    if not source_reference.startswith("https://www.copel.com/"):
        raise ValueError("Copel source must use the official HTTPS host")
    text = _plain_text(html_document).lower()
    if "capivari" not in text or "abertura das comportas" not in text:
        raise ValueError("notice does not explicitly describe Capivari gate opening")
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html_document)
    if not match:
        raise ValueError(
            "official notice has no machine-readable publication timestamp"
        )
    published = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    if published.tzinfo is None:
        raise ValueError("official notice publication timestamp is not timezone-aware")
    return CopelOperationEvent(
        reservoir_provider_id="COPEL_CAPIVARI",
        reservoir_name="Capivari",
        river_name="Capivari",
        event_type="GATE_OPENING",
        published_at=published.astimezone(timezone.utc),
        effective_at=None,
        numeric_value=None,
        unit=None,
        description_sanitized="Official notice explicitly reports increased gate opening at Capivari; no numerical flow is inferred.",
        source_reference=source_reference,
    )


class CopelPublicNoticeAdapter:
    source_reference = (
        "https://www.copel.com/site/noticias/"
        "copel-mantem-reservatorios-abertos-para-verter-agua-das-chuvas-em-usinas-dos-rios-iguacu-tibagi-e-capivari/"
    )

    def list_stations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.EMPTY_VALID_RESULT,
            detail="Copel notice source has no station inventory",
        )

    def fetch_observations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.EMPTY_VALID_RESULT,
            detail="Copel notice source has no hydrological observations",
        )

    def health_check(self) -> HydroFetchResult:
        try:
            event = parse_copel_capivari_notice(
                _fetch_text(self.source_reference), self.source_reference
            )
            return HydroFetchResult(
                HydroFetchStatus.SUCCESS, (event,), "official Capivari notice parsed"
            )
        except urllib.error.HTTPError as exc:
            status = (
                HydroFetchStatus.RATE_LIMITED
                if exc.code == 429
                else HydroFetchStatus.SOURCE_UNAVAILABLE
            )
            return HydroFetchResult(status, detail=f"official notice HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError):
            return HydroFetchResult(
                HydroFetchStatus.SOURCE_UNAVAILABLE,
                detail="official notice unavailable",
            )
        except ValueError as exc:
            return HydroFetchResult(HydroFetchStatus.PARSE_ERROR, detail=str(exc))


def parse_noaa_cpc_enso(text: str, source_reference: str) -> EnsoContext:
    issued = re.search(
        r"(?:issued\s+by[\s\S]{0,160}?|issued\s+(?:on\s+)?)"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if not issued:
        raise ValueError("NOAA CPC issue date not found")
    issued_on = datetime.strptime(issued.group(1), "%d %B %Y").date()
    lowered = text.lower()
    if "el niño" in lowered or "el nino" in lowered:
        state = "EL_NINO"
    elif "la niña" in lowered or "la nina" in lowered:
        state = "LA_NINA"
    elif "neutral" in lowered:
        state = "NEUTRAL"
    else:
        raise ValueError("NOAA CPC ENSO state not found")
    probability_match = re.search(
        r"(?:El Niño|El Nino|La Niña|La Nina)[^.]{0,120}?(\d{1,3})\s*%|"
        r"(\d{1,3})\s*%[^.]{0,120}(?:El Niño|El Nino|La Niña|La Nina)",
        text,
        re.IGNORECASE,
    )
    probability = (
        float(next(value for value in probability_match.groups() if value is not None))
        if probability_match
        else None
    )
    window = re.search(r"\b([A-Z]{3}\s+\d{4})\b", text)
    strength = "VERY_STRONG" if "very strong" in lowered else None
    return EnsoContext(
        provider="NOAA_CPC",
        issued_on=issued_on,
        valid_window=window.group(1) if window else None,
        enso_state=state,
        probability=probability,
        strength_category=strength,
        source_reference=source_reference,
    )


class NoaaCpcEnsoAdapter:
    source_reference = (
        "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
        "enso_advisory/ensodisc.html"
    )

    def list_stations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.EMPTY_VALID_RESULT,
            detail="climate context has no station inventory",
        )

    def fetch_observations(self) -> HydroFetchResult:
        return HydroFetchResult(
            HydroFetchStatus.EMPTY_VALID_RESULT,
            detail="climate context is not a hydrological observation",
        )

    def health_check(self) -> HydroFetchResult:
        try:
            context = parse_noaa_cpc_enso(
                _plain_text(_fetch_text(self.source_reference)), self.source_reference
            )
            return HydroFetchResult(
                HydroFetchStatus.SUCCESS, (context,), "official NOAA CPC context parsed"
            )
        except urllib.error.HTTPError as exc:
            status = (
                HydroFetchStatus.RATE_LIMITED
                if exc.code == 429
                else HydroFetchStatus.SOURCE_UNAVAILABLE
            )
            return HydroFetchResult(status, detail=f"NOAA CPC HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError):
            return HydroFetchResult(
                HydroFetchStatus.SOURCE_UNAVAILABLE, detail="NOAA CPC unavailable"
            )
        except ValueError as exc:
            return HydroFetchResult(HydroFetchStatus.PARSE_ERROR, detail=str(exc))


def _health_projection(status: HydroFetchStatus) -> tuple[str, str | None]:
    if status in {HydroFetchStatus.SUCCESS, HydroFetchStatus.EMPTY_VALID_RESULT}:
        return "AVAILABLE", None
    if status == HydroFetchStatus.STALE:
        return "STALE", status.value
    if status in {HydroFetchStatus.PARSE_ERROR, HydroFetchStatus.RATE_LIMITED}:
        return "DEGRADED", status.value
    return "SOURCE_UNAVAILABLE", status.value


class HydroEvidenceStore(Protocol):
    def upsert_source_health(
        self,
        provider: str,
        status: str,
        *,
        last_attempt: str | None = None,
        last_success: str | None = None,
        last_observation: str | None = None,
        latency_seconds: float | None = None,
        failure_code: str | None = None,
        failure_detail_sanitized: str | None = None,
    ) -> None: ...

    def record_reservoir_operation_event(self, event: CopelOperationEvent) -> bool: ...

    def record_climate_context(
        self, context: EnsoContext, *, fetched_at: str
    ) -> bool: ...


def ingest_public_evidence(store: HydroEvidenceStore) -> dict[str, int | str]:
    """Persist only current, explicit public Copel and NOAA facts plus health.

    The store is intentionally duck-typed so no global adapter is introduced
    into the tenant application service.  This command is safe to rerun: the
    database uniqueness contracts make published evidence idempotent.
    """
    now = datetime.now(timezone.utc).isoformat()
    adapters: tuple[tuple[str, HydrologySourceAdapter], ...] = (
        ("ANA_HIDROWEB", AnaHidroWebAdapter()),
        ("SAISP", SaispPublicAdapter()),
        ("CEMADEN_PED", CemadenPedAdapter()),
        ("COPEL", CopelPublicNoticeAdapter()),
        ("NOAA_CPC", NoaaCpcEnsoAdapter()),
    )
    result: dict[str, int | str] = {"reservoir_events": 0, "climate_context": 0}
    for provider, adapter in adapters:
        checked = adapter.health_check()
        status, failure_code = _health_projection(checked.status)
        success = (
            now
            if checked.status
            in {HydroFetchStatus.SUCCESS, HydroFetchStatus.EMPTY_VALID_RESULT}
            else None
        )
        store.upsert_source_health(
            provider,
            status,
            last_attempt=now,
            last_success=success,
            failure_code=failure_code,
            failure_detail_sanitized=checked.detail[:500] if failure_code else None,
        )
        if provider == "COPEL" and checked.status == HydroFetchStatus.SUCCESS:
            for item in checked.items:
                if isinstance(
                    item, CopelOperationEvent
                ) and store.record_reservoir_operation_event(item):
                    result["reservoir_events"] = int(result["reservoir_events"]) + 1
        if provider == "NOAA_CPC" and checked.status == HydroFetchStatus.SUCCESS:
            for item in checked.items:
                if isinstance(item, EnsoContext) and store.record_climate_context(
                    item, fetched_at=now
                ):
                    result["climate_context"] = int(result["climate_context"]) + 1
        result[provider] = checked.status.value
    return result


class ValeDoRibeiraSituationService:
    """Read-only view over global facts; unknown is a valid operational result."""

    def __init__(self, store: object) -> None:
        self.store = store

    def build(self) -> dict[str, object]:
        generated_at = datetime.now(timezone.utc).isoformat()
        if not hasattr(self.store, "vale_do_ribeira_situation"):
            base: dict[str, object] = {
                "source_health": [],
                "rainfall_summary": {
                    "status": "UNKNOWN",
                    "reason": "GLOBAL_HYDRO_STORAGE_UNAVAILABLE",
                },
                "river_summary": {
                    "status": "UNKNOWN",
                    "reason": "GLOBAL_HYDRO_STORAGE_UNAVAILABLE",
                },
                "reservoir_events": [],
                "climate_context": [],
                "active_alerts": [],
                "unknowns": ["Global hydrology storage is unavailable"],
                "evidence": {
                    "scope_geometry_status": "UNKNOWN",
                    "scope_reference": None,
                },
            }
        else:
            base = self.store.vale_do_ribeira_situation()  # type: ignore[attr-defined]
        return {"generated_at": generated_at, **base}
