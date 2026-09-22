"""Loopback-only static frontend server for the private runtime phase."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .logging_config import configure_structured_logging


LOGGER = logging.getLogger(__name__)


class FrontendHandler(SimpleHTTPRequestHandler):
    _MAX_PROXY_BODY_BYTES = 1_048_576

    def __init__(
        self, *args: Any, directory: str, api_origin: str | None = None, **kwargs: Any
    ) -> None:
        self.api_origin = api_origin
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info(
            "static request",
            extra={"status": str(args[1]) if len(args) > 1 else "UNKNOWN"},
        )

    def do_GET(self) -> None:  # noqa: N802 - standard library handler hook
        if self.path.startswith("/api/"):
            self._proxy_api()
            return
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

    def do_POST(self) -> None:  # noqa: N802 - standard library handler hook
        if self.path.startswith("/api/"):
            self._proxy_api()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _proxy_api(self) -> None:
        if not self.api_origin:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        target = f"{self.api_origin}{self.path.removeprefix('/api')}"
        data: bytes | None = None
        if self.command == "POST":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
                return
            if not 0 <= content_length <= self._MAX_PROXY_BODY_BYTES:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            data = self.rfile.read(content_length)
        request = urllib.request.Request(
            target,
            data=data,
            method=self.command,
            headers={
                key: value
                for key, value in self.headers.items()
                if key.lower() in {"authorization", "accept", "content-type"}
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310 -- fixed loopback origin
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get_content_type())
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as error:
            body = error.read()
            self.send_response(error.code)
            self.send_header("Content-Type", error.headers.get_content_type())
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.URLError:
            self.send_error(HTTPStatus.BAD_GATEWAY)

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
    parser.add_argument("--api-origin", default=None)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1"} or not 1 <= args.port <= 65535:
        raise ValueError("static server must use a loopback host and valid port")
    if args.api_origin not in {None, "http://127.0.0.1:8080"}:
        raise ValueError("api proxy must use the fixed loopback API origin")
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise RuntimeError("frontend build directory does not exist")
    configure_structured_logging()
    handler = lambda *items, **kwargs: FrontendHandler(  # noqa: E731
        *items, directory=str(root), api_origin=args.api_origin, **kwargs
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
