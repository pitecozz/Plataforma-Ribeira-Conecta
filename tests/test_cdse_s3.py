from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from botocore.exceptions import ClientError

from ribeira_platform.cdse_s3 import (
    AssetAccessStatus,
    AssetCredentials,
    CdseS3AssetAdapter,
    CdseS3Config,
    parse_cdse_s3_reference,
)
from ribeira_platform.object_storage import LocalObjectStorage


class _Credentials:
    def get_credentials(self):
        return AssetCredentials("test-access-key", "test-secret-key")


class _Body:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        return None


class _S3:
    def __init__(self, payload: bytes = b"asset"):
        self.payload = payload

    def head_object(self, **kwargs):
        return {"ContentLength": len(self.payload), "ChecksumSHA256": "provider"}

    def get_object(self, **kwargs):
        return {"Body": _Body(self.payload)}


class CdseS3AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = LocalObjectStorage(Path(self.temp.name) / "objects")
        self.config = CdseS3Config(
            max_object_bytes=1024,
            max_job_bytes=2048,
            chunk_bytes=2,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_reference_requires_exact_cdse_bucket_and_safe_key(self):
        parsed = parse_cdse_s3_reference("s3://eodata/path/file.jp2", self.config)
        self.assertEqual(parsed.object_key, "path/file.jp2")
        for href in (
            "s3://other-bucket/path/file.jp2",
            "s3://127.0.0.1/path/file.jp2",
            "s3://metadata/path/file.jp2",
            "https://eodata/path/file.jp2",
            "s3://eodata/../file.jp2",
        ):
            with self.subTest(href=href):
                with self.assertRaises(Exception):
                    parse_cdse_s3_reference(href, self.config)

    def test_missing_credentials_is_blocked_without_client_call(self):
        adapter = CdseS3AssetAdapter(
            self.storage,
            credential_provider=type(
                "Missing", (), {"get_credentials": lambda _: None}
            )(),
            config=self.config,
            client_factory=lambda *_: self.fail("client must not be created"),
        )
        result = adapter.download("s3://eodata/path/file.jp2", "assets/file.jp2")
        self.assertEqual(result.status, AssetAccessStatus.BLOCKED_BY_CREDENTIAL)
        self.assertIsNone(result.local_reference)

    def test_controlled_stream_download_records_local_checksum(self):
        adapter = CdseS3AssetAdapter(
            self.storage,
            credential_provider=_Credentials(),
            config=self.config,
            client_factory=lambda *_: _S3(b"abcdef"),
        )
        result = adapter.download("s3://eodata/path/file.jp2", "assets/file.jp2")
        self.assertEqual(result.status, AssetAccessStatus.SUCCEEDED)
        self.assertEqual(result.bytes_downloaded, 6)
        self.assertEqual(result.checksum_algorithm, "SHA-256")
        self.assertIsNotNone(result.checksum_local)
        self.assertEqual(
            self.storage.read_local_path(result.local_reference or ""),
            str(Path(self.temp.name) / "objects" / "assets" / "file.jp2"),
        )

    def test_oversized_object_is_rejected_before_download(self):
        adapter = CdseS3AssetAdapter(
            self.storage,
            credential_provider=_Credentials(),
            config=self.config,
            client_factory=lambda *_: _S3(b"x" * 2048),
        )
        result = adapter.download("s3://eodata/path/file.jp2", "assets/file.jp2")
        self.assertEqual(result.status, AssetAccessStatus.ASSET_TOO_LARGE)
        self.assertEqual(result.failure_code, "OBJECT_SIZE_LIMIT")

    def test_authentication_error_is_redacted(self):
        marker = "redacted-marker"

        class Failing:
            def head_object(self, **kwargs):
                raise ClientError(
                    {"Error": {"Code": "AccessDenied", "Message": marker}},
                    "HeadObject",
                )

        adapter = CdseS3AssetAdapter(
            self.storage,
            credential_provider=_Credentials(),
            config=self.config,
            client_factory=lambda *_: Failing(),
        )
        result = adapter.download("s3://eodata/path/file.jp2", "assets/file.jp2")
        self.assertEqual(
            result.status, AssetAccessStatus.PROVIDER_AUTHENTICATION_FAILED
        )
        self.assertNotIn(marker, str(result))
        self.assertNotIn(marker, result.failure_code or "")
