from __future__ import annotations

import hashlib
import json
import os
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
        self, root: str | Path | None = None, max_object_bytes: int = 50_000_000
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
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        checksum = hashlib.sha256(payload).hexdigest()
        return f"local://{key}", checksum

    def put_json(self, key: str, payload: Any) -> tuple[str, str]:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return self.put_bytes(key, encoded, "application/json")

    def read_local_path(self, reference: str) -> str:
        if not reference.startswith("local://"):
            raise ObjectStorageError(
                "only local object references can be processed locally"
            )
        path = self._path(reference.removeprefix("local://"))
        if not path.is_file():
            raise ObjectStorageError("object does not exist")
        return str(path)
