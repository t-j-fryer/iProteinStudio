#!/usr/bin/env python3
"""Generate or install equivalent Codex and Claude MCP configurations safely."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List


PROFILES = ("read", "run", "admin")
CLIENTS = ("codex", "claude", "claude-code", "claude-desktop", "both", "local-desktops")
START = "# BEGIN IPROTEINSTUDIO MCP (generated)"
END = "# END IPROTEINSTUDIO MCP (generated)"


def server_path() -> Path:
    return Path(__file__).resolve().with_name("server.py")


def root_path() -> Path:
    configured = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEINSTUDIO_TEST_SUPPORT_ROOT")
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".iproteinstudio").resolve()


def selected_profiles(text: str) -> List[str]:
    values = [value.strip() for value in text.split(",") if value.strip()]
    unknown = sorted(set(values) - set(PROFILES))
    if unknown or not values:
        raise SystemExit(f"Profiles must be a comma-separated subset of {', '.join(PROFILES)}")
    if "admin" in values and os.environ.get("IPROTEINSTUDIO_ENABLE_ADMIN_MCP") != "1":
        raise SystemExit("The admin profile is disabled by default. Set IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1 for an explicit installation.")
    return list(dict.fromkeys(values))


def codex_block(profiles: List[str]) -> str:
    blocks = [START]
    for profile in profiles:
        blocks.extend(
            [
                f"[mcp_servers.iproteinstudio-{profile}]",
                'command = "/usr/bin/python3"',
                f'args = [{json.dumps(str(server_path()))}, "--profile", "{profile}"]',
                (
                    f'env = {{ NANOHUNTER_ROOT = {json.dumps(str(root_path()))}, '
                    'IPROTEINSTUDIO_ENABLE_ADMIN_MCP = "1" }'
                    if profile == "admin"
                    else f'env = {{ NANOHUNTER_ROOT = {json.dumps(str(root_path()))} }}'
                ),
                "startup_timeout_sec = 20",
                "tool_timeout_sec = 60",
                "",
            ]
        )
    blocks.append(END)
    return "\n".join(blocks) + "\n"


def replace_marked(text: str, block: str) -> str:
    if START in text or END in text:
        if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
            raise SystemExit("Existing Codex config has malformed iProteinStudio markers; repair it manually before retrying.")
        before = text[: text.index(START)].rstrip()
        after = text[text.index(END) + len(END) :].strip()
        return "\n\n".join(value for value in (before, block.strip(), after) if value) + "\n"
    if any(f"[mcp_servers.iproteinstudio-{profile}]" in text for profile in PROFILES):
        raise SystemExit("Codex already contains unmanaged iproteinstudio-* entries. Remove or rename them before using Studio's one-click integration.")
    return text.rstrip() + ("\n\n" if text.strip() else "") + block


def remove_marked(text: str) -> str:
    if START not in text and END not in text:
        return text
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise SystemExit("Existing Codex config has malformed iProteinStudio markers; repair it manually before retrying.")
    before = text[: text.index(START)].rstrip()
    after = text[text.index(END) + len(END) :].strip()
    rendered = "\n\n".join(value for value in (before, after) if value)
    return rendered + ("\n" if rendered else "")


def atomic_write(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def configure_codex(path: Path, profiles: List[str], write: bool, remove: bool = False) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rendered = remove_marked(existing) if remove else replace_marked(existing, codex_block(profiles))
    if write:
        if remove and not rendered and path.exists():
            path.unlink()
        elif rendered or not remove:
            atomic_write(path, rendered)
        print(f"{'Removed iProteinStudio from' if remove else 'Configured'} Codex: {path}")
    else:
        action = "remove the marked iProteinStudio block from" if remove else "write iProteinStudio MCP profiles to"
        print(f"Would {action} Codex config {path}")


def claude_servers(profiles: List[str], include_type: bool = True) -> Dict[str, object]:
    servers: Dict[str, object] = {}
    for profile in profiles:
        environment = {"NANOHUNTER_ROOT": str(root_path())}
        if profile == "admin":
            environment["IPROTEINSTUDIO_ENABLE_ADMIN_MCP"] = "1"
        record: Dict[str, object] = {
            "command": "/usr/bin/python3",
            "args": [str(server_path()), "--profile", profile],
            "env": environment,
        }
        if include_type:
            record["type"] = "stdio"
        servers[f"iproteinstudio-{profile}"] = record
    return servers


def configure_claude_json(path: Path, profiles: List[str], write: bool, remove: bool = False, label: str = "Claude", include_type: bool = True) -> None:
    if remove and not path.exists():
        print(f"No {label} iProteinStudio configuration was present: {path}")
        return
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Existing {label} MCP config is invalid JSON: {exc}")
        if not isinstance(payload, dict):
            raise SystemExit(f"Existing {label} MCP config must be a JSON object.")
    else:
        payload = {}
    servers = payload.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise SystemExit("Existing .mcp.json mcpServers value must be an object.")
    for name in list(servers):
        if name.startswith("iproteinstudio-"):
            del servers[name]
    if not remove:
        servers.update(claude_servers(profiles, include_type=include_type))
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if write:
        atomic_write(path, rendered)
        print(f"{'Removed iProteinStudio from' if remove else 'Configured'} {label}: {path}")
    else:
        print(f"Would {'remove iProteinStudio from' if remove else 'write'} {label} config {path}")


def configure_claude_project(path: Path, profiles: List[str], write: bool, remove: bool = False) -> None:
    configure_claude_json(path, profiles, write, remove, "Claude Code project")


def claude_desktop_path() -> Path:
    override = os.environ.get("IPROTEINSTUDIO_CLAUDE_DESKTOP_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def configure_claude_user(profiles: List[str], write: bool, remove: bool = False) -> None:
    executable = shutil.which("claude")
    commands = []
    for profile in profiles:
        if remove:
            commands.append([executable or "claude", "mcp", "remove", "--scope", "user", f"iproteinstudio-{profile}"])
        else:
            command = [executable or "claude", "mcp", "add", "--scope", "user", f"iproteinstudio-{profile}", "--env", f"NANOHUNTER_ROOT={root_path()}"]
            if profile == "admin":
                command += ["--env", "IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1"]
            commands.append(command + ["--", "/usr/bin/python3", str(server_path()), "--profile", profile])
    if not write:
        for command in commands:
            print("Would run: " + " ".join(json.dumps(value) for value in command))
        return
    if not executable:
        raise SystemExit("Claude Code is not installed or not on PATH; use --scope project or install Claude first.")
    for command in commands:
        completed = subprocess.run(command)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)


def codex_status(path: Path) -> Dict[str, object]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if START in text and END in text:
        valid_markers = text.count(START) == 1 and text.count(END) == 1 and text.index(START) < text.index(END)
    else:
        valid_markers = START not in text and END not in text
    marked = text[text.index(START) : text.index(END)] if valid_markers and START in text else ""
    profiles = [profile for profile in PROFILES if f"mcp_servers.iproteinstudio-{profile}" in marked]
    unmanaged = not marked and any(f"[mcp_servers.iproteinstudio-{profile}]" in text for profile in PROFILES)
    return {"configured": bool(profiles), "profiles": profiles, "path": str(path), "invalid": not valid_markers or unmanaged}


def claude_json_status(path: Path) -> Dict[str, object]:
    payload: Dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            return {"configured": False, "profiles": [], "path": str(path), "invalid": True}
    servers = payload.get("mcpServers", {})
    if not isinstance(servers, dict):
        return {"configured": False, "profiles": [], "path": str(path), "invalid": True}
    profiles = [profile for profile in PROFILES if isinstance(servers, dict) and f"iproteinstudio-{profile}" in servers]
    return {"configured": bool(profiles), "profiles": profiles, "path": str(path), "invalid": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=CLIENTS, default="both")
    parser.add_argument("--scope", choices=["project", "user"], default="project")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--profiles", default="read,run")
    parser.add_argument("--write", action="store_true", help="Apply changes; without this flag, print a dry run.")
    parser.add_argument("--remove", action="store_true", help="Remove only iProteinStudio's entries and preserve unrelated client configuration.")
    parser.add_argument("--status", action="store_true", help="Print local desktop integration status as JSON without changing configuration.")
    args = parser.parse_args()
    if args.status and (args.write or args.remove):
        parser.error("--status cannot be combined with --write or --remove")
    profiles = selected_profiles(args.profiles)
    project = args.project_root.expanduser().resolve()
    codex_enabled = args.client in {"codex", "both", "local-desktops"}
    claude_code_enabled = args.client in {"claude", "claude-code", "both"}
    claude_desktop_enabled = args.client in {"claude-desktop", "local-desktops"}
    codex_target = project / ".codex" / "config.toml" if args.scope == "project" else Path.home() / ".codex" / "config.toml"
    desktop_target = claude_desktop_path()
    if args.status:
        report: Dict[str, object] = {}
        if codex_enabled:
            report["codex"] = codex_status(codex_target)
        if claude_desktop_enabled:
            report["claude_desktop"] = claude_json_status(desktop_target)
        if claude_code_enabled:
            report["claude_code"] = {"available": bool(shutil.which("claude")), "status_requires_cli": True}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if codex_enabled:
        target = project / ".codex" / "config.toml" if args.scope == "project" else Path.home() / ".codex" / "config.toml"
        configure_codex(target, profiles, args.write, args.remove)
    if claude_code_enabled:
        if args.scope == "project":
            configure_claude_project(project / ".mcp.json", profiles, args.write, args.remove)
        else:
            configure_claude_user(profiles, args.write, args.remove)
    if claude_desktop_enabled:
        configure_claude_json(desktop_target, profiles, args.write, args.remove, "Claude Desktop", include_type=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
