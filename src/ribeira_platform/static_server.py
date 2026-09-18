"""Loopback-only static frontend server for the private runtime phase."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .logging_config import configure_structured_logging


LOGGER = logging.getLogger(__name__)


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str, **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info(
            "static request",
            extra={"status": str(args[1]) if len(args) > 1 else "UNKNOWN"},
        )

    def do_GET(self) -> None:  # noqa: N802 - standard library handler hook
        if self.path == "/health/live":
            self._health({"status": "ok", "service": "ribeira-static"})
            return
        if self.path == "/health/ready":
            index = Path(self.directory or ".") / "index.html"
            if index.is_file():
                self._health({"status": "ready", "service": "ribeira-static"})
            else:
                self._health(
                    {"status": "not_ready", "dependency": "frontend_build"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return
        super().do_GET()

    def _health(
        self, payload: dict[str, str], status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ribeira loopback static frontend")
    parser.add_argument("--root", default="frontend/dist")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1"} or not 1 <= args.port <= 65535:
        raise ValueError("static server must use a loopback host and valid port")
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise RuntimeError("frontend build directory does not exist")
    configure_structured_logging()
    handler = lambda *items, **kwargs: FrontendHandler(  # noqa: E731
        *items, directory=str(root), **kwargs
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)

    def stop(_: int, __: object) -> None:
        LOGGER.info("static server graceful shutdown requested")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOGGER.info("static server listening on loopback")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
