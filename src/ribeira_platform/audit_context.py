from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_request_id: ContextVar[str | None] = ContextVar("ribeira_request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar(
    "ribeira_correlation_id", default=None
)


@contextmanager
def request_context(request_id: str, correlation_id: str) -> Iterator[None]:
    request_token = _request_id.set(request_id)
    correlation_token = _correlation_id.set(correlation_id)
    try:
        yield
    finally:
        _request_id.reset(request_token)
        _correlation_id.reset(correlation_token)


def current_context() -> tuple[str | None, str | None]:
    return _request_id.get(), _correlation_id.get()
