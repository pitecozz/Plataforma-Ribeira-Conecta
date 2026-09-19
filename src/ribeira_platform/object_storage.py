from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ObjectStorageError(ValueError):
    pass


class LocalObjectStorage:
    """Development-safe object storage adapter.

    References are opaque ``local://`` keys. The adapter never follows remote
    URLs and prevents path traversal outside its configured root.
    """

    def __init__(
        self, root: str | Path | None = None, max_object_bytes: int = 500_000_000
    ):
        root_value = (
            root or os.getenv("RIBEIRA_OBJECT_STORAGE_ROOT") or ".local/object-storage"
        )
        self.root = Path(root_value)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_object_bytes = max_object_bytes

    def _path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise ObjectStorageError("unsafe object key")
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise ObjectStorageError("object path escapes storage root")
        return path

    def put_bytes(self, key: str, payload: bytes, media_type: str) -> tuple[str, str]:
        if len(payload) > self.max_object_bytes:
            raise ObjectStorageError("object exceeds configured size limit")
        # Keep the same atomic-replace property as ``put_file``.  Import
        # evidence must never expose a partially written original file after a
        # process interruption.
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        checksum = hashlib.sha256(payload).hexdigest()
        return f"local://{key}", checksum

    def put_json(self, key: str, payload: Any) -> tuple[str, str]:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return self.put_bytes(key, encoded, "application/json")

    def put_file(
        self,
        key: str,
        source: str | Path,
        media_type: str | None = None,
        max_bytes: int | None = None,
    ) -> tuple[str, str, int]:
        """Atomically store a bounded local file and calculate its SHA-256.

        The source is deliberately accepted only as a local path. Remote asset
        adapters must perform their own validation and streaming before handing
        a file to this adapter.
        """
        source_path = Path(source)
        if not source_path.is_file():
            raise ObjectStorageError("source file does not exist")
        limit = (
            self.max_object_bytes
            if max_bytes is None
            else min(max_bytes, self.max_object_bytes)
        )
        size = source_path.stat().st_size
        if size > limit:
            raise ObjectStorageError("object exceeds configured size limit")
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        digest = hashlib.sha256()
        copied = 0
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=f".{destination.name}.", delete=False
            ) as temporary:
                temporary_name = temporary.name
                with source_path.open("rb") as input_file:
                    while True:
                        chunk = input_file.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > limit:
                            raise ObjectStorageError(
                                "object exceeds configured size limit"
                            )
                        digest.update(chunk)
                        temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        return f"local://{key}", digest.hexdigest(), copied

    def read_local_path(self, reference: str) -> str:
        if not reference.startswith("local://"):
            raise ObjectStorageError(
                "only local object references can be processed locally"
            )
        path = self._path(reference.removeprefix("local://"))
        if not path.is_file():
            raise ObjectStorageError("object does not exist")
        return str(path)
