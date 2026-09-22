from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ribeira_platform.static_server import FrontendHandler


class _UpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - standard library hook
        self._respond()

    def do_POST(self) -> None:  # noqa: N802 - standard library hook
        self._respond()

    def _respond(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        payload = json.dumps(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        ).encode("utf-8")
        self.send_response(
            HTTPStatus.CREATED if self.command == "POST" else HTTPStatus.OK
        )
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class StaticIngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        Path(self.directory.name, "index.html").write_text("<title>Ribeira</title>")
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
        self.upstream_thread = threading.Thread(
            target=self.upstream.serve_forever, daemon=True
        )
        self.upstream_thread.start()
        origin = f"http://127.0.0.1:{self.upstream.server_port}"

        def handler(*args: Any, **kwargs: Any) -> FrontendHandler:
            return FrontendHandler(
                *args,
                directory=self.directory.name,
                api_origin=origin,
                **kwargs,
            )

        self.ingress = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.ingress_thread = threading.Thread(
            target=self.ingress.serve_forever, daemon=True
        )
        self.ingress_thread.start()
        self.base_url = f"http://127.0.0.1:{self.ingress.server_port}"

    def tearDown(self) -> None:
        self.ingress.shutdown()
        self.ingress.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.directory.cleanup()

    def test_api_get_is_stripped_and_forwards_authorization_only_to_api(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/properties?limit=1",
            headers={"Authorization": "Bearer pilot-token"},
        )
        with urllib.request.urlopen(request) as response:  # nosec B310 -- local test server
            payload = json.loads(response.read())
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/v1/properties?limit=1")
        self.assertEqual(payload["authorization"], "Bearer pilot-token")

    def test_api_post_forwards_a_bounded_body(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/tenants/example/pilot-feedback",
            data=b'{"feedback_type":"USEFUL"}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:  # nosec B310 -- local test server
            self.assertEqual(response.status, HTTPStatus.CREATED)
            payload = json.loads(response.read())
        self.assertEqual(payload["method"], "POST")
        self.assertEqual(payload["path"], "/v1/tenants/example/pilot-feedback")
        self.assertEqual(payload["body"], '{"feedback_type":"USEFUL"}')

    def test_non_api_post_and_metrics_are_not_exposed_by_ingress(self) -> None:
        for request in (
            urllib.request.Request(f"{self.base_url}/metrics"),
            urllib.request.Request(
                f"{self.base_url}/not-api", data=b"x", method="POST"
            ),
        ):
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(request)  # nosec B310 -- local test server
            self.assertEqual(failure.exception.code, HTTPStatus.NOT_FOUND)
