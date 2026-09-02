#!/usr/bin/env python3
"""Generate or install equivalent Codex and Claude MCP configurations safely."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


PROFILES = ("read", "run", "admin")
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
    return text.rstrip() + ("\n\n" if text.strip() else "") + block


def configure_codex(path: Path, profiles: List[str], write: bool) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rendered = replace_marked(existing, codex_block(profiles))
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.part")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
        print(f"Configured Codex: {path}")
    else:
        print(f"Would write Codex config {path}:\n{codex_block(profiles)}")


def claude_servers(profiles: List[str]) -> Dict[str, object]:
    servers: Dict[str, object] = {}
    for profile in profiles:
        environment = {"NANOHUNTER_ROOT": str(root_path())}
        if profile == "admin":
            environment["IPROTEINSTUDIO_ENABLE_ADMIN_MCP"] = "1"
        servers[f"iproteinstudio-{profile}"] = {
            "type": "stdio",
            "command": "/usr/bin/python3",
            "args": [str(server_path()), "--profile", profile],
            "env": environment,
        }
    return servers


def configure_claude_project(path: Path, profiles: List[str], write: bool) -> None:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Existing Claude project MCP config is invalid JSON: {exc}")
        if not isinstance(payload, dict):
            raise SystemExit("Existing Claude project MCP config must be a JSON object.")
    else:
        payload = {}
    servers = payload.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise SystemExit("Existing .mcp.json mcpServers value must be an object.")
    for name in list(servers):
        if name.startswith("iproteinstudio-"):
            del servers[name]
    servers.update(claude_servers(profiles))
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.part")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
        print(f"Configured Claude Code: {path}")
    else:
        print(f"Would write Claude project config {path}:\n{rendered}")


def configure_claude_user(profiles: List[str], write: bool) -> None:
    executable = shutil.which("claude")
    commands = []
    for profile in profiles:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["codex", "claude", "both"], default="both")
    parser.add_argument("--scope", choices=["project", "user"], default="project")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--profiles", default="read,run")
    parser.add_argument("--write", action="store_true", help="Apply changes; without this flag, print a dry run.")
    args = parser.parse_args()
    profiles = selected_profiles(args.profiles)
    project = args.project_root.expanduser().resolve()
    if args.client in {"codex", "both"}:
        target = project / ".codex" / "config.toml" if args.scope == "project" else Path.home() / ".codex" / "config.toml"
        configure_codex(target, profiles, args.write)
    if args.client in {"claude", "both"}:
        if args.scope == "project":
            configure_claude_project(project / ".mcp.json", profiles, args.write)
        else:
            configure_claude_user(profiles, args.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
