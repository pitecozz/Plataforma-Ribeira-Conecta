from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .models import RuleDefinition, new_id, now_utc, to_jsonable
from .epistemology import RuleAuthority
from .service import RibeiraApplication
from .storage import SQLiteStore


def _json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    value = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


class RibeiraHandler(BaseHTTPRequestHandler):
    application: RibeiraApplication

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/health":
            self._send(200, {"status": "ok", "service": "ribeira-platform", "epistemic_policy": "no_imputation"})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = [part for part in urlparse(self.path).path.split("/") if part]
        try:
            body = _json_body(self)
            if path == ["v1", "tenants"]:
                tenant = self.application.create_tenant(str(body["name"]))
                self._send(201, to_jsonable(tenant))
                return
            if len(path) == 4 and path[:2] == ["v1", "tenants"] and path[3] == "properties":
                property = self.application.create_property(path[2], str(body["name"]), body.get("geometry_geojson"), body.get("geometry_crs"))
                self._send(201, to_jsonable(property))
                return
            if len(path) == 4 and path[:2] == ["v1", "tenants"] and path[3] == "sources":
                source = self.application.create_source(path[2], str(body["name"]), str(body["source_type"]), str(body["provider"]), body.get("endpoint"), body.get("source_version"))
                self._send(201, to_jsonable(source))
                return
            if len(path) == 4 and path[:2] == ["v1", "tenants"] and path[3] == "rules":
                rule = RuleDefinition(
                    id=str(body.get("id", new_id())), tenant_id=path[2], version=int(body["version"]), name=str(body["name"]),
                    authority=RuleAuthority(str(body["authority"])), metric=str(body["metric"]), operator=str(body["operator"]),
                    threshold=float(body["threshold"]), unit=str(body["unit"]), severity=str(body["severity"]), status=str(body["status"]),
                    approved_by=body.get("approved_by"), valid_from=str(body.get("valid_from", now_utc())), valid_until=body.get("valid_until"),
                )
                self._send(201, to_jsonable(self.application.create_rule(rule)))
                return
            if len(path) == 7 and path[:2] == ["v1", "tenants"] and path[3] == "properties" and path[5] == "ingestions":
                result = self.application.ingest(path[2], path[4], path[6], str(body.get("actor", "api")))
                self._send(200, to_jsonable(result))
                return
            if len(path) == 6 and path[:2] == ["v1", "tenants"] and path[3] == "properties" and path[5] == "evaluate":
                result = self.application.evaluate(path[2], path[4], str(body.get("actor", "api")))
                self._send(200, to_jsonable(result))
                return
            self._send(404, {"error": "not_found"})
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": "invalid_request", "detail": str(exc)})
        except LookupError as exc:
            self._send(404, {"error": "not_found", "detail": str(exc)})
        except PermissionError as exc:
            self._send(403, {"error": "forbidden", "detail": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive API boundary
            self._send(500, {"error": "internal_error", "detail": type(exc).__name__})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    path = os.environ.get("RIBEIRA_DB_PATH", "ribeira-local.sqlite3")
    host = os.environ.get("RIBEIRA_API_HOST", "127.0.0.1")
    port = int(os.environ.get("RIBEIRA_API_PORT", "8080"))
    application = RibeiraApplication(SQLiteStore(path))
    RibeiraHandler.application = application
    server = ThreadingHTTPServer((host, port), RibeiraHandler)
    print(f"Ribeira API listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        application.store.close()


if __name__ == "__main__":
    main()
