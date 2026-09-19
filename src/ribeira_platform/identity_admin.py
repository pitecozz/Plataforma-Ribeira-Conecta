"""Private host-only CLI for controlled OIDC membership provisioning."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .identity_provisioning import (
    ExternalIdentityProvisioningRequest,
    ExternalMembershipRevocationRequest,
    IdentityProvisioningService,
    ProvisioningConflict,
    ProvisioningNotFound,
    ProvisioningRequestError,
)
from .postgres import PostgresStore


def _load_secure_json(path: Path) -> dict[str, Any]:
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProvisioningRequestError("provisioning request file is invalid") from exc
    with os.fdopen(descriptor, encoding="utf-8") as handle:
        metadata = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
        ):
            raise ProvisioningRequestError("provisioning request file is not secure")
        try:
            payload: Any = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ProvisioningRequestError(
                "provisioning request file is invalid"
            ) from exc
    if not isinstance(payload, dict):
        raise ProvisioningRequestError("provisioning request fields are invalid")
    return payload


def load_request_file(path: Path) -> ExternalIdentityProvisioningRequest:
    payload = _load_secure_json(path)
    if set(payload) != {
        "external_issuer",
        "external_subject",
        "tenant_id",
        "role",
        "operator_actor",
    }:
        raise ProvisioningRequestError("provisioning request fields are invalid")
    request = ExternalIdentityProvisioningRequest(**payload)
    request.validate()
    return request


def load_revocation_request_file(path: Path) -> ExternalMembershipRevocationRequest:
    payload = _load_secure_json(path)
    if set(payload) != {
        "external_issuer",
        "external_subject",
        "tenant_id",
        "expected_role",
        "operator_actor",
    }:
        raise ProvisioningRequestError("revocation request fields are invalid")
    request = ExternalMembershipRevocationRequest(**payload)
    request.validate()
    return request


def provision(request_file: Path, *, dry_run: bool) -> int:
    request = load_request_file(request_file)
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise ProvisioningRequestError("RIBEIRA_DATABASE_URL is required")
    store = PostgresStore(dsn)
    try:
        result = IdentityProvisioningService(
            store
        ).provision_external_identity_membership(request, dry_run=dry_run)
    finally:
        store.close()
    print("REQUEST_FILE=SECURE")
    print(f"IDENTITY={result.identity}")
    print("TENANT=FOUND")
    print("ROLE=VIEWER")
    print(f"MEMBERSHIP={result.membership}")
    print(f"AUDIT={result.audit}")
    if dry_run:
        print("DRY_RUN=PASS")
    return 0


def revoke(request_file: Path, *, dry_run: bool) -> int:
    request = load_revocation_request_file(request_file)
    dsn = os.getenv("RIBEIRA_DATABASE_URL")
    if not dsn:
        raise ProvisioningRequestError("RIBEIRA_DATABASE_URL is required")
    store = PostgresStore(dsn)
    try:
        result = IdentityProvisioningService(store).revoke_external_identity_membership(
            request, dry_run=dry_run
        )
    finally:
        store.close()
    print("REQUEST_FILE=SECURE")
    print("IDENTITY=FOUND")
    print("TENANT=FOUND")
    print("MEMBERSHIP=FOUND")
    print(f"ROLE={result.role}")
    print(f"CURRENT_STATUS={result.current_status}")
    print(f"ACTION={result.action}")
    print(f"AUDIT={result.audit}")
    if dry_run:
        print("DRY_RUN=PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Private Ribeira OIDC identity administration"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    provision_parser = subcommands.add_parser("provision")
    provision_parser.add_argument("--request-file", type=Path, required=True)
    provision_parser.add_argument("--dry-run", action="store_true")
    revoke_parser = subcommands.add_parser("revoke")
    revoke_parser.add_argument("--request-file", type=Path, required=True)
    revoke_parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "provision":
            raise SystemExit(
                provision(arguments.request_file, dry_run=arguments.dry_run)
            )
        if arguments.command == "revoke":
            raise SystemExit(revoke(arguments.request_file, dry_run=arguments.dry_run))
    except ProvisioningConflict:
        print("PROVISIONING=CONFLICT", file=sys.stderr)
        raise SystemExit(2)
    except ProvisioningNotFound:
        print("PROVISIONING=NOT_FOUND", file=sys.stderr)
        raise SystemExit(2)
    except ProvisioningRequestError:
        print("PROVISIONING=INVALID_REQUEST", file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        print("PROVISIONING=FAILED", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
