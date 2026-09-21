"""Small, fail-closed Sentinel Hub OAuth and Process API client."""

from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .flood_sar import PROCESS_ENDPOINT, TOKEN_ENDPOINT


class SentinelHubError(RuntimeError):
    """Sanitized external-provider failure; never includes response body or credentials."""


@dataclass(frozen=True)
class SentinelHubCredentials:
    client_id: str
    client_secret: str


def load_private_credentials(path: Path) -> SentinelHubCredentials:
    status = path.lstat() if path.exists() else None
    if status is None or path.is_symlink() or not stat.S_ISREG(status.st_mode):
        raise SentinelHubError("credential file is not a regular non-symlink file")
    if stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.getuid():
        raise SentinelHubError("credential file permissions or owner are unsafe")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().removeprefix("export ").strip()
        values[normalized_key] = value.strip().strip('"').strip("'")
    client_id = values.get("CDSE_SH_CLIENT_ID", "")
    client_secret = values.get("CDSE_SH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SentinelHubError("required Sentinel Hub credentials are missing")
    return SentinelHubCredentials(client_id=client_id, client_secret=client_secret)


class SentinelHubClient:
    def __init__(
        self, credentials: SentinelHubCredentials, *, timeout_seconds: int = 90
    ):
        self._credentials = credentials
        self._timeout_seconds = timeout_seconds
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token is not None:
            return self._access_token
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
            }
        ).encode()
        request = urllib.request.Request(TOKEN_ENDPOINT, data=body, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                document = json.loads(response.read())
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
        ) as exc:
            raise SentinelHubError("Sentinel Hub OAuth token request failed") from exc
        token = document.get("access_token")
        if not isinstance(token, str) or not token:
            raise SentinelHubError("Sentinel Hub OAuth response has no access token")
        self._access_token = token
        return token

    def process(self, payload: dict[str, object]) -> bytes:
        request = urllib.request.Request(
            PROCESS_ENDPOINT,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "image/tiff")
        request.add_header("Authorization", f"Bearer {self._token()}")
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                content_type = response.headers.get_content_type()
                payload_bytes = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise SentinelHubError("Sentinel Hub Process API request failed") from exc
        if content_type not in {
            "image/tiff",
            "image/geotiff",
            "application/octet-stream",
        }:
            raise SentinelHubError(
                "Sentinel Hub Process API did not return analytical TIFF"
            )
        if len(payload_bytes) < 1024:
            raise SentinelHubError(
                "Sentinel Hub Process API TIFF response is unexpectedly small"
            )
        return payload_bytes
