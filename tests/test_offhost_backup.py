from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ribeira_platform.offhost_backup import (
    BACKUP_FILES,
    S3BackupConfiguration,
    S3BackupTransport,
    validate_backup_directory,
)


class _ExplicitProviderDouble:
    """Classified unit-test double, not an off-host evidence source."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.upload_order: list[str] = []

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()
        self.upload_order.append(key.rsplit("/", 1)[-1])

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict[str, object]:
        return {"Contents": []}


class OffHostBackupTests(unittest.TestCase):
    def _backup(self, root: Path) -> Path:
        directory = root / "20260918T010203Z"
        directory.mkdir()
        contents = {
            "postgres.dump": b"postgres",
            "object-storage.tar": b"objects",
            "runtime.env.example": b"nonsecret example",
            "SHA256SUMS": b"",
        }
        checksums = {
            name: hashlib.sha256(value).hexdigest()
            for name, value in contents.items()
            if name != "SHA256SUMS"
        }
        contents["SHA256SUMS"] = "".join(
            f"{digest}  {name}\n" for name, digest in checksums.items()
        ).encode()
        for name, content in contents.items():
            (directory / name).write_bytes(content)
        (directory / "backup-manifest.json").write_text(
            json.dumps(
                {
                    "backup_version": 1,
                    "backup_id": directory.name,
                    "migration_state": [{"version": "014", "checksum": "test"}],
                    "files": checksums,
                }
            )
        )
        return directory

    def test_manifest_last_upload_and_verified_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._backup(root)
            remote = _ExplicitProviderDouble()
            transport = S3BackupTransport(
                S3BackupConfiguration(bucket="test", prefix="private"), remote
            )
            self.assertEqual(transport.upload(source), source.name)
            self.assertEqual(remote.upload_order[-1], "backup-manifest.json")
            restored = transport.download(source.name, root / "restored")
            self.assertEqual(
                validate_backup_directory(restored)["backup_id"], source.name
            )

    def test_incomplete_or_tampered_backup_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = self._backup(Path(temporary))
            (source / "postgres.dump").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                validate_backup_directory(source)

    def test_only_expected_files_are_part_of_transport_contract(self) -> None:
        self.assertIn("backup-manifest.json", BACKUP_FILES)
        self.assertNotIn("cdse.env", BACKUP_FILES)


if __name__ == "__main__":
    unittest.main()
