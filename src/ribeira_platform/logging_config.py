"""Minimal structured logging for private Ribeira runtime processes."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from .audit_context import current_context


SENSITIVE_KEYS = {
    "access_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id, correlation_id = current_context()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "correlation_id",
            "tenant_id",
            "job_id",
            "status",
            "failure_code",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if request_id and "request_id" not in payload:
            payload["request_id"] = request_id
        if correlation_id and "correlation_id" not in payload:
            payload["correlation_id"] = correlation_id
        for key, value in record.__dict__.items():
            lowered = key.lower()
            if any(sensitive in lowered for sensitive in SENSITIVE_KEYS):
                payload[key] = "[REDACTED]"
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_structured_logging() -> None:
    """Configure stdout JSON once, for journald collection by systemd."""
    root = logging.getLogger()
    if getattr(root, "_ribeira_structured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root._ribeira_structured = True  # type: ignore[attr-defined]
