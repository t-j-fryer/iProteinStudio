#!/usr/bin/env python3
"""Manage the local half of an opt-in iProteinStudio remote MCP gateway."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict

from iprotein_mcp.common import StudioError, agent_root, atomic_json, load_json, process_alive, stable_environment, utc_now


def directory() -> Path:
    value = agent_root() / "remote"
    value.mkdir(parents=True, exist_ok=True)
    return value


def token_path() -> Path:
    return directory() / "capability-token"


def state_path() -> Path:
    return directory() / "state.json"


def ensure_token(rotate: bool = False) -> str:
    path = token_path()
    if rotate or not path.exists():
        temporary = path.with_name(f".{path.name}.{os.getpid()}.part")
        temporary.write_text(secrets.token_urlsafe(48) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    os.chmod(path, 0o600)
    return path.read_text(encoding="utf-8").strip()


def status() -> Dict[str, Any]:
    try:
        value = load_json(state_path())
    except StudioError:
        return {"running": False, "configured": token_path().is_file()}
    running = process_alive(value.get("pid"))
    value["running"] = running
    if not running and value.get("status") == "running":
        value["status"] = "stopped"
        value["stopped_at"] = utc_now()
        atomic_json(state_path(), value)
    return value


def start(profile: str, port: int) -> Dict[str, Any]:
    if port < 1024 or port > 65535:
        raise StudioError("Remote gateway port must be between 1024 and 65535.")
    current = status()
    if current.get("running"):
        if current.get("profile") != profile or int(current.get("port", 0)) != port:
            raise StudioError("A remote gateway is already running with different settings. Stop it before changing access.")
        return current
    # Every new listener gets a new capability. In particular, a URL shared for
    # read-only access can never silently become run-capable after a restart.
    token = ensure_token(rotate=True)
    bridge = Path(__file__).resolve().parent
    log_path = directory() / "gateway.log"
    command = ["/usr/bin/caffeinate", "-i", sys.executable, str(bridge / "remote_server.py"), "--profile", profile, "--bind", "127.0.0.1", "--port", str(port), "--token-file", str(token_path())]
    log_descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    process_id = os.fork()
    if process_id == 0:
        try:
            os.setsid()
            null_descriptor = os.open(os.devnull, os.O_RDONLY)
            os.dup2(null_descriptor, 0)
            os.dup2(log_descriptor, 1)
            os.dup2(log_descriptor, 2)
            os.close(null_descriptor)
            os.close(log_descriptor)
            os.chdir(bridge)
            os.execve(command[0], command, stable_environment())
        except BaseException:
            os._exit(127)
    os.close(log_descriptor)
    value = {
        "schema_version": 1, "status": "starting", "running": True,
        "pid": process_id, "process_group": process_id, "profile": profile,
        "bind": "127.0.0.1", "port": port, "started_at": utc_now(),
        "local_endpoint": f"http://127.0.0.1:{port}/mcp/{token}",
        "credential_warning": "The endpoint path is a secret. Use it only through an HTTPS or private-network proxy.",
        "sleep_policy": "The Mac is kept awake while this gateway is running.",
    }
    atomic_json(state_path(), value)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not process_alive(process_id):
            value.update({"status": "failed", "running": False})
            atomic_json(state_path(), value)
            raise StudioError(f"Remote gateway stopped during startup. See {log_path}.")
        try:
            health = urllib.request.Request(f"http://127.0.0.1:{port}/health", headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(health, timeout=0.3) as response:
                if response.status == 200:
                    value["status"] = "running"
                    atomic_json(state_path(), value)
                    return value
        except Exception:
            time.sleep(0.1)
    os.killpg(process_id, signal.SIGTERM)
    raise StudioError("Remote gateway did not become ready within five seconds.")


def stop() -> Dict[str, Any]:
    value = status()
    process_group = value.get("process_group")
    if value.get("running") and process_group:
        try:
            os.killpg(int(process_group), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and process_alive(value.get("pid")):
            time.sleep(0.05)
        if process_alive(value.get("pid")):
            try:
                os.killpg(int(process_group), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
    value.update({"status": "stopped", "running": False, "stopped_at": utc_now()})
    atomic_json(state_path(), value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    launch = sub.add_parser("start")
    launch.add_argument("--profile", choices=["read", "run"], default="read")
    launch.add_argument("--port", type=int, default=8765)
    sub.add_parser("stop")
    sub.add_parser("rotate-token")
    args = parser.parse_args()
    try:
        if args.command == "status": value = status()
        elif args.command == "start": value = start(args.profile, args.port)
        elif args.command == "stop": value = stop()
        else:
            stop()
            ensure_token(rotate=True)
            value = {"rotated": True, "running": False}
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except StudioError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
