"""Small S3-compatible off-host backup transport.

The backup manifest is uploaded last: an interrupted transfer therefore never
looks like a restorable backup.  Credentials are obtained only by boto3's
normal server-side credential chain and are never read, rendered, or logged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3


BACKUP_VERSION = 1
BACKUP_FILES = (
    "postgres.dump",
    "object-storage.tar",
    "runtime.env.example",
    "SHA256SUMS",
    "backup-manifest.json",
)
CHECKSUMMED_FILES = BACKUP_FILES[:3]


class ObjectDestination(Protocol):
    def upload_file(self, Filename: str, Bucket: str, Key: str) -> Any: ...

    def download_file(self, Bucket: str, Key: str, Filename: str) -> Any: ...

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class S3BackupConfiguration:
    bucket: str
    prefix: str = "ribeira-backups"
    endpoint_url: str | None = None
    region: str | None = None

    @classmethod
    def from_environment(cls) -> "S3BackupConfiguration":
        bucket = os.getenv("RIBEIRA_BACKUP_S3_BUCKET", "").strip()
        if not bucket:
            raise ValueError("RIBEIRA_BACKUP_S3_BUCKET is required")
        return cls(
            bucket=bucket,
            prefix=os.getenv("RIBEIRA_BACKUP_S3_PREFIX", "ribeira-backups").strip("/"),
            endpoint_url=os.getenv("RIBEIRA_BACKUP_S3_ENDPOINT_URL") or None,
            region=os.getenv("RIBEIRA_BACKUP_S3_REGION") or None,
        )


def _key(config: S3BackupConfiguration, backup_id: str, filename: str) -> str:
    if not backup_id or "/" in backup_id or filename not in BACKUP_FILES:
        raise ValueError("invalid backup object key")
    return "/".join(part for part in (config.prefix, backup_id, filename) if part)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_backup_directory(directory: Path) -> dict[str, Any]:
    manifest_path = directory / "backup-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("backup manifest is unavailable or invalid") from exc
    if manifest.get("backup_version") != BACKUP_VERSION:
        raise ValueError("unsupported backup manifest version")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(CHECKSUMMED_FILES):
        raise ValueError("backup manifest file set is invalid")
    for name, expected in files.items():
        path = directory / name
        if (
            not path.is_file()
            or not isinstance(expected, str)
            or _checksum(path) != expected
        ):
            raise ValueError(f"backup checksum mismatch: {name}")
    checksum_lines = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    expected_lines = {f"{digest}  {name}" for name, digest in files.items()}
    if set(checksum_lines) != expected_lines:
        raise ValueError("backup SHA256SUMS does not match manifest")
    return manifest


class S3BackupTransport:
    def __init__(
        self, config: S3BackupConfiguration, client: ObjectDestination
    ) -> None:
        self.config = config
        self.client = client

    def upload(self, directory: Path) -> str:
        manifest = validate_backup_directory(directory)
        backup_id = str(manifest.get("backup_id", ""))
        if backup_id != directory.name:
            raise ValueError("backup manifest identity does not match directory")
        # Manifest is the completion marker and must always be uploaded last.
        for filename in BACKUP_FILES[:-1]:
            self.client.upload_file(
                str(directory / filename),
                self.config.bucket,
                _key(self.config, backup_id, filename),
            )
        self.client.upload_file(
            str(directory / "backup-manifest.json"),
            self.config.bucket,
            _key(self.config, backup_id, "backup-manifest.json"),
        )
        return backup_id

    def download(self, backup_id: str, destination: Path) -> Path:
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            # A manifest is required before any backup is considered complete.
            self.client.download_file(
                self.config.bucket,
                _key(self.config, backup_id, "backup-manifest.json"),
                str(destination / "backup-manifest.json"),
            )
            manifest = json.loads(
                (destination / "backup-manifest.json").read_text(encoding="utf-8")
            )
            if manifest.get("backup_id") != backup_id:
                raise ValueError("remote backup manifest identity mismatch")
            for filename in BACKUP_FILES[:-1]:
                self.client.download_file(
                    self.config.bucket,
                    _key(self.config, backup_id, filename),
                    str(destination / filename),
                )
            validate_backup_directory(destination)
            return destination
        except Exception:
            for child in destination.iterdir():
                child.unlink()
            destination.rmdir()
            raise


def _client(config: S3BackupConfiguration) -> ObjectDestination:
    return boto3.client(
        "s3", endpoint_url=config.endpoint_url, region_name=config.region
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ribeira S3-compatible off-host backup transport"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    upload = sub.add_parser("upload")
    upload.add_argument("directory", type=Path)
    download = sub.add_parser("download")
    download.add_argument("backup_id")
    download.add_argument("destination", type=Path)
    args = parser.parse_args()
    config = S3BackupConfiguration.from_environment()
    transport = S3BackupTransport(config, _client(config))
    if args.command == "upload":
        print(transport.upload(args.directory))
    else:
        print(transport.download(args.backup_id, args.destination))


if __name__ == "__main__":
    main()
