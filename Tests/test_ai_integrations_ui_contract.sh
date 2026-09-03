#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIEW="${ROOT}/Sources/iProteinStudio/Core/AIIntegrationService.swift"
CONFIGURE="${ROOT}/Sources/iProteinStudio/Resources/pipeline/mcp/configure.py"
REMOTE="${ROOT}/Sources/iProteinStudio/Resources/pipeline/mcp/remote_server.py"

rg -Fq 'Button("Enable \(client.label)")' "${VIEW}" || { echo "FAIL missing one-click enable action" >&2; exit 1; }
rg -q 'Read only' "${VIEW}" || { echo "FAIL missing read-only access choice" >&2; exit 1; }
rg -q 'Claude Desktop' "${VIEW}" || { echo "FAIL missing Claude Desktop integration" >&2; exit 1; }
rg -q 'ChatGPT and phone access' "${VIEW}" || { echo "FAIL missing remote-access disclosure" >&2; exit 1; }
rg -q 'local-desktops' "${CONFIGURE}" || { echo "FAIL missing local desktop configuration target" >&2; exit 1; }
rg -q 'claude_desktop_config.json' "${CONFIGURE}" || { echo "FAIL missing Claude Desktop config boundary" >&2; exit 1; }
rg -q 'IPROTEINSTUDIO_ALLOW_REMOTE_BIND' "${REMOTE}" || { echo "FAIL remote server can bind publicly without explicit opt-in" >&2; exit 1; }
rg -q 'choices=\["read", "run"\]' "${REMOTE}" || { echo "FAIL remote transport exposes an unexpected profile" >&2; exit 1; }
! rg -q 'choices=\[[^]]*admin' "${REMOTE}" || { echo "FAIL remote transport exposes admin" >&2; exit 1; }

echo "PASS AI desktop and remote integration UI contract"
