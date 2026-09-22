"""Private, audited bootstrap of one verified pilot import package.

This module deliberately has no HTTP route.  It is a host-only operator tool
for the otherwise circular first-tenant bootstrap: an OIDC membership cannot
exist before its tenant exists.  It accepts a small, evidence-preserving
GeoJSON/manifest contract, validates it before writing, and uses deterministic
identifiers derived from immutable file checksums so a repeated command cannot
silently duplicate a customer workspace.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import stat
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .business import Asset, CommercialClassification
from .boundaries import validate_boundary
from .epistemology import DataClassification
from .models import new_id, now_utc
from .postgres import PostgresStore
from .service import RibeiraApplication


BOOTSTRAP_EVENT = "PILOT_BOOTSTRAP_COMPLETED"
BOOTSTRAP_NAMESPACE = uuid.UUID("7d011658-3ed2-4e1b-9af4-2a35b18ec40d")
MAX_IMPORT_BYTES = 1_000_000


class BootstrapError(ValueError):
    """The operator package is incomplete, unsafe, or internally inconsistent."""


class BootstrapConflict(RuntimeError):
    """The deterministic bootstrap target is partially populated or mismatched."""


@dataclass(frozen=True)
class PlannedAsset:
    id: str
    name: str
    asset_type: str
    geometry: dict[str, Any]
    classification: CommercialClassification


@dataclass(frozen=True)
class PilotBootstrapPlan:
    fingerprint: str
    manifest_sha256: str
    geojson_sha256: str
    tenant_id: str
    tenant_name: str
    customer_id: str
    customer_name: str
    property_id: str
    property_name: str
    customer_property_id: str
    boundary_geometry: dict[str, Any]
    boundary_source: str
    boundary_classification: DataClassification
    boundary_usage: str
    legal_boundary_verified: bool
    assets: tuple[PlannedAsset, ...]
    excluded_feature_names: tuple[str, ...]


def _read_private_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise BootstrapError("pilot import file is unavailable") from exc
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
        ):
            raise BootstrapError("pilot import file is not private and operator-owned")
        content = handle.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise BootstrapError("pilot import file exceeds size limit")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("pilot import file is not valid JSON") from exc
    if not isinstance(document, dict):
        raise BootstrapError("pilot import document must be an object")
    return document, hashlib.sha256(content).hexdigest()


def _required_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BootstrapError(f"pilot manifest requires {key}")
    return value.strip()


def _id(fingerprint: str, suffix: str) -> str:
    return str(uuid.uuid5(BOOTSTRAP_NAMESPACE, f"{fingerprint}:{suffix}"))


def _classification(value: Any) -> CommercialClassification:
    try:
        return CommercialClassification(value)
    except ValueError as exc:
        raise BootstrapError("asset classification is unsupported") from exc


def _data_classification(value: Any) -> DataClassification:
    try:
        return DataClassification(value)
    except ValueError as exc:
        raise BootstrapError("boundary classification is unsupported") from exc


def load_plan(manifest_path: Path, geojson_path: Path) -> PilotBootstrapPlan:
    """Validate a private package and construct its deterministic write plan."""
    manifest, manifest_sha256 = _read_private_json(manifest_path)
    geojson, geojson_sha256 = _read_private_json(geojson_path)
    if geojson.get("type") != "FeatureCollection" or not isinstance(
        geojson.get("features"), list
    ):
        raise BootstrapError("pilot GeoJSON must be a FeatureCollection")

    property_name = _required_string(manifest, "property_name")
    customer_name = _required_string(manifest, "pilot_customer_label")
    source = _required_string(manifest, "source")
    crs = _required_string(manifest, "crs")
    if crs.upper() not in {"EPSG:4326", "CRS:84"}:
        raise BootstrapError("pilot manifest CRS must be EPSG:4326 or CRS:84")
    boundary_manifest = manifest.get("boundary")
    if not isinstance(boundary_manifest, dict):
        raise BootstrapError("pilot manifest requires boundary object")
    boundary_name = _required_string(boundary_manifest, "placemark_name")
    if boundary_manifest.get("confirmed_by_operator") is not True:
        raise BootstrapError("pilot boundary is not confirmed by operator")
    if boundary_manifest.get("legal_boundary_verified") is not False:
        raise BootstrapError("pilot boundary legal state must remain explicitly false")
    boundary_usage = _required_string(boundary_manifest, "intended_use")
    included_assets = manifest.get("included_assets")
    if (
        not isinstance(included_assets, list)
        or not included_assets
        or any(
            not isinstance(item, str) or not item.strip() for item in included_assets
        )
        or len(set(included_assets)) != len(included_assets)
    ):
        raise BootstrapError("pilot manifest included_assets must be unique names")
    excluded = manifest.get("excluded_features")
    if not isinstance(excluded, dict) or any(
        not isinstance(name, str) or not isinstance(reason, str) or not reason.strip()
        for name, reason in excluded.items()
    ):
        raise BootstrapError("pilot manifest excluded_features is invalid")

    features: dict[str, dict[str, Any]] = {}
    for feature in geojson["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise BootstrapError("pilot GeoJSON contains an invalid feature")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise BootstrapError("pilot GeoJSON feature lacks properties or geometry")
        name = properties.get("name")
        if not isinstance(name, str) or not name.strip() or name in features:
            raise BootstrapError(
                "pilot GeoJSON feature names must be unique and nonempty"
            )
        if properties.get("crs", "").upper() not in {"EPSG:4326", "CRS:84"}:
            raise BootstrapError("pilot GeoJSON feature CRS is unsupported")
        if properties.get("source") != source:
            raise BootstrapError("pilot GeoJSON feature source does not match manifest")
        features[name] = feature

    boundary_feature = features.get(boundary_name)
    if boundary_feature is None:
        raise BootstrapError("pilot boundary feature is absent")
    boundary_properties = boundary_feature["properties"]
    if boundary_properties.get("entity_kind") != "property_boundary":
        raise BootstrapError("pilot boundary entity kind is invalid")
    if boundary_properties.get("usage") != boundary_usage:
        raise BootstrapError("pilot boundary usage does not match manifest")
    if boundary_properties.get("legal_boundary_verified") is not False:
        raise BootstrapError("pilot boundary legal state does not match manifest")
    boundary_classification = _data_classification(
        boundary_properties.get("classification")
    )
    boundary_geometry = boundary_feature["geometry"]
    validate_boundary(boundary_geometry, crs)

    asset_features = [
        item
        for item in features.values()
        if item["properties"].get("entity_kind") == "asset"
    ]
    asset_names = [str(item["properties"]["name"]) for item in asset_features]
    if set(asset_names) != set(included_assets) or len(asset_names) != len(
        included_assets
    ):
        raise BootstrapError("pilot GeoJSON assets do not exactly match manifest")
    if set(features) != {boundary_name, *included_assets}:
        raise BootstrapError("pilot GeoJSON contains unapproved features")

    fingerprint = hashlib.sha256(
        f"{manifest_sha256}:{geojson_sha256}".encode("ascii")
    ).hexdigest()
    planned_assets: list[PlannedAsset] = []
    for name in included_assets:
        feature = features[name]
        properties = feature["properties"]
        asset_type = properties.get("asset_type")
        if not isinstance(asset_type, str) or not asset_type.strip():
            raise BootstrapError("pilot asset type is required")
        # Reuse the domain model's CRS and geometry validation before dry-run
        # output.  No write is attempted for malformed field geometry.
        Asset(
            _id(fingerprint, f"asset:{name}"),
            _id(fingerprint, "tenant"),
            asset_type,
            name,
            None,
            "ACTIVE",
            _id(fingerprint, "property"),
            None,
            _classification(properties.get("classification")),
            feature["geometry"],
            "EPSG:4326",
        )
        planned_assets.append(
            PlannedAsset(
                _id(fingerprint, f"asset:{name}"),
                name,
                asset_type,
                feature["geometry"],
                _classification(properties.get("classification")),
            )
        )
    return PilotBootstrapPlan(
        fingerprint,
        manifest_sha256,
        geojson_sha256,
        _id(fingerprint, "tenant"),
        customer_name,
        _id(fingerprint, "customer"),
        customer_name,
        _id(fingerprint, "property"),
        property_name,
        _id(fingerprint, "customer-property"),
        boundary_geometry,
        source,
        boundary_classification,
        boundary_usage,
        False,
        tuple(planned_assets),
        tuple(sorted(excluded)),
    )


def _existing_state(store: PostgresStore, plan: PilotBootstrapPlan) -> str:
    """Return EMPTY or COMPLETE; refuse unsafe partial/mismatched retries."""
    with store.tenant_transaction(None, platform_admin=True):
        tenant = store.connection.execute(
            "SELECT id,name FROM tenant WHERE id=%s", (plan.tenant_id,)
        ).fetchone()
        if tenant is None:
            return "EMPTY"
        if tenant["name"] != plan.tenant_name:
            raise BootstrapConflict(
                "deterministic tenant identifier has different data"
            )
    with store.tenant_transaction(plan.tenant_id, platform_admin=True):
        customer = store.connection.execute(
            "SELECT id,display_name FROM customer WHERE id=%s", (plan.customer_id,)
        ).fetchone()
        property_item = store.get_property(plan.tenant_id, plan.property_id)
        link = store.connection.execute(
            "SELECT id FROM customer_property WHERE id=%s", (plan.customer_property_id,)
        ).fetchone()
        assets = store.connection.execute(
            "SELECT id,name FROM asset WHERE property_id=%s ORDER BY id",
            (plan.property_id,),
        ).fetchall()
    if customer is None or property_item is None or link is None:
        raise BootstrapConflict("pilot bootstrap is partially populated")
    if (
        customer["display_name"] != plan.customer_name
        or property_item.name != plan.property_name
    ):
        raise BootstrapConflict("pilot bootstrap persisted data does not match package")
    expected_assets = {(asset.id, asset.name) for asset in plan.assets}
    if {(str(item["id"]), str(item["name"])) for item in assets} != expected_assets:
        raise BootstrapConflict("pilot bootstrap assets do not match package")
    return "COMPLETE"


def _valid_from() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_plan(
    store: PostgresStore, plan: PilotBootstrapPlan, *, actor: str, dry_run: bool
) -> str:
    """Execute the complete plan atomically or return an idempotent result."""
    if not actor.strip():
        raise BootstrapError("operator actor is required")
    state = _existing_state(store, plan)
    if state == "COMPLETE":
        return "EXISTS"
    if dry_run:
        return "WOULD_CREATE"
    application = RibeiraApplication(store)  # type: ignore[arg-type]
    provenance = (
        f"{plan.boundary_source}; manifest_sha256={plan.manifest_sha256}; "
        f"geojson_sha256={plan.geojson_sha256}"
    )
    with store.transaction():
        application.create_tenant(
            plan.tenant_name, tenant_id=plan.tenant_id, actor=actor
        )
        application.business.create_customer(
            plan.tenant_id,
            plan.customer_name,
            actor=actor,
            platform_admin=True,
            customer_id=plan.customer_id,
        )
        application.create_property(
            plan.tenant_id,
            plan.property_name,
            plan.boundary_geometry,
            "EPSG:4326",
            platform_admin=True,
            boundary_source=plan.boundary_source,
            classification=plan.boundary_classification,
            actor=actor,
            property_id=plan.property_id,
        )
        application.business.link_customer_property(
            plan.tenant_id,
            plan.customer_id,
            plan.property_id,
            "OPERATIONAL_ANALYSIS",
            _valid_from(),
            None,
            actor,
            link_id=plan.customer_property_id,
        )
        for item in plan.assets:
            application.business.register_asset(
                Asset(
                    item.id,
                    plan.tenant_id,
                    item.asset_type,
                    item.name,
                    None,
                    "ACTIVE",
                    plan.property_id,
                    None,
                    item.classification,
                    item.geometry,
                    "EPSG:4326",
                    provenance,
                    None,
                    {
                        "import_fingerprint": plan.fingerprint,
                        "source": plan.boundary_source,
                        "observed_at": "UNKNOWN",
                    },
                ),
                actor=actor,
                platform_admin=True,
            )
        with store.tenant_transaction(plan.tenant_id, platform_admin=True):
            store.audit(
                plan.tenant_id,
                actor,
                BOOTSTRAP_EVENT,
                "pilot_bootstrap",
                plan.property_id,
                {
                    "fingerprint": plan.fingerprint,
                    "manifest_sha256": plan.manifest_sha256,
                    "geojson_sha256": plan.geojson_sha256,
                    "boundary_source": plan.boundary_source,
                    "boundary_classification": plan.boundary_classification.value,
                    "boundary_usage": plan.boundary_usage,
                    "legal_boundary_verified": plan.legal_boundary_verified,
                    "asset_count": len(plan.assets),
                    "excluded_feature_names": list(plan.excluded_feature_names),
                },
                new_id(),
                now_utc(),
            )
    return "CREATED"


def _print_plan(plan: PilotBootstrapPlan, result: str, dry_run: bool) -> None:
    print("IMPORT_FILES=VALID")
    print(f"BOOTSTRAP={result}")
    print(f"DRY_RUN={'PASS' if dry_run else 'NO'}")
    print(f"TENANT_ID={plan.tenant_id}")
    print(f"PROPERTY_ID={plan.property_id}")
    print(f"BOUNDARY_CLASSIFICATION={plan.boundary_classification.value}")
    print(f"LEGAL_BOUNDARY_VERIFIED={str(plan.legal_boundary_verified).upper()}")
    print(f"ASSET_COUNT={len(plan.assets)}")
    print("ASSET_NAMES=" + ",".join(item.name for item in plan.assets))
    print("EXCLUDED_FEATURES=" + ",".join(plan.excluded_feature_names))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Private audited pilot package bootstrap"
    )
    parser.add_argument("--manifest-file", type=Path, required=True)
    parser.add_argument("--geojson-file", type=Path, required=True)
    parser.add_argument(
        "--operator-actor", default=f"LOCAL_OPERATOR:{getpass.getuser()}"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        plan = load_plan(args.manifest_file, args.geojson_file)
        dsn = os.getenv("RIBEIRA_DATABASE_URL")
        if not dsn:
            raise BootstrapError("RIBEIRA_DATABASE_URL is required")
        store = PostgresStore(dsn)
        try:
            result = execute_plan(
                store, plan, actor=args.operator_actor, dry_run=args.dry_run
            )
        finally:
            store.close()
        _print_plan(plan, result, args.dry_run)
    except (BootstrapError, BootstrapConflict) as exc:
        print("PILOT_BOOTSTRAP=FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
