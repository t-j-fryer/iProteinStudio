#!/usr/bin/env python3
"""Authenticated stateless Streamable-HTTP transport for the Studio MCP bridge.

This process intentionally provides HTTP, not public exposure or TLS. Keep it
on loopback and place it behind a separately approved HTTPS tunnel or reverse
proxy. The random capability path is a credential and must not be logged or
shared beyond the chosen MCP client.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import stat
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from iprotein_mcp import __version__
from iprotein_mcp.common import StudioError
from server import MCPServer


MAX_REQUEST_BYTES = 2_000_000


def load_token(path: Path) -> str:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise StudioError(f"Could not read the remote gateway credential: {exc}") from exc
    if mode & 0o077:
        raise StudioError("The remote gateway credential must not be readable by group or other users (mode 0600).")
    if len(value) < 32:
        raise StudioError("The remote gateway credential is too short; rotate it before starting.")
    return value


def is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


class MCPHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], profile: str, token: str):
        self.mcp = MCPServer(profile)
        self.profile = profile
        self.token = token
        self.dispatch_lock = threading.Lock()
        super().__init__(address, MCPRequestHandler)


class MCPRequestHandler(BaseHTTPRequestHandler):
    server: MCPHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        # Never let the capability-bearing request path reach standard logs.
        sys.stderr.write(f"remote-mcp {self.client_address[0]} {args[1] if len(args) > 1 else ''}\n")

    def _json(self, status: int, value: Dict[str, Any]) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        request_path = self.path.split("?", 1)[0]
        expected_path = f"/mcp/{self.server.token}"
        path_token_ok = hmac.compare_digest(request_path, expected_path)
        authorization = self.headers.get("Authorization", "")
        bearer_ok = request_path == "/mcp" and authorization.startswith("Bearer ") and hmac.compare_digest(authorization[7:], self.server.token)
        return path_token_ok or bearer_ok

    def _health_authorized(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        return authorization.startswith("Bearer ") and hmac.compare_digest(authorization[7:], self.server.token)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/health":
            if self._health_authorized():
                self._json(HTTPStatus.OK, {"ok": True, "version": __version__})
            else:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "This stateless gateway accepts MCP requests with POST."})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_REQUEST_BYTES else HTTPStatus.BAD_REQUEST, {"error": "invalid request size"})
            return
        try:
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            if "id" not in request:
                self.send_response(HTTPStatus.ACCEPTED)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            try:
                with self.server.dispatch_lock:
                    result = self.server.mcp.dispatch(request)
                response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
            except StudioError as exc:
                response = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": str(exc)}}
            self._json(HTTPStatus.OK, response)
        except Exception as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Invalid MCP JSON: {exc}"}})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["read", "run"], default="read")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()
    if not is_loopback(args.bind) and os.environ.get("IPROTEINSTUDIO_ALLOW_REMOTE_BIND") != "1":
        parser.error("non-loopback binding requires IPROTEINSTUDIO_ALLOW_REMOTE_BIND=1; prefer an authenticated HTTPS proxy to loopback")
    token = load_token(args.token_file)
    server = MCPHTTPServer((args.bind, args.port), args.profile, token)
    address, port = server.server_address[:2]
    print(json.dumps({"ready": True, "bind": address, "port": port, "profile": args.profile}), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
