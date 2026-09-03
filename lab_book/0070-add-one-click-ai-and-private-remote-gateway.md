---
entry: 0070
title: Add one-click AI clients and a private remote gateway
date: 2026-09-02
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [mcp, codex, claude, chatgpt, remote, security, ui]
---

## Context

Entry [[0069-add-client-neutral-agent-bridge]] provided the client-neutral MCP
backend and a command-line configuration helper. That was sufficient for a
developer but not for the intended end user: downloading iProteinStudio should
not require editing configuration or opening Terminal. The same discussion also
raised remote delegation from an AI application on a phone. Local desktop MCP
uses stdio, whereas ChatGPT's app integration needs a network-reachable HTTPS
MCP service; those cannot safely be presented as the same operation.

## What was done

- Added **AI** to the workspace toolbar and **AI assistants** to application
  Settings. Users can enable, update, open or remove Codex and Claude Desktop
  integration with buttons and choose `read only` or `read + run` access.
- Made the app stage its current bridge before registration and call the same
  configuration utility used by tests. Codex is registered at user scope;
  Claude Desktop receives its native `mcpServers` command/arguments/environment
  shape. Existing unrelated TOML or JSON content is preserved, malformed client
  configuration fails visibly, and removal deletes only `iproteinstudio-*`.
- Kept Claude Code as a separate target in `configure.py`; its CLI/project route
  is not conflated with Claude Desktop. Added machine-readable status and
  removal operations for desktop onboarding.
- Added an in-app bridge health check. It stages the packaged server and runs
  `studioctl.py doctor`, checking all profiles and versioned schemas without
  starting a model.
- Added a distinct stateless Streamable-HTTP transport for remote clients. It
  accepts only `read` or `run`, never `admin`; requires a random 48-byte
  capability token stored mode 0600; accepts that secret as bearer auth or an
  unguessable URL path; limits requests to 2 MB; suppresses secret paths from
  its own logs; and binds to loopback unless a separate environment opt-in is
  supplied.
- Added a durable gateway controller with status/start/stop/token rotation,
  readiness checking, bounded process-group termination, validated user ports
  and `caffeinate -i` only while remote access is enabled. It uses the same MCP
  tools, immutable plans, audit records and serialized job broker as local
  clients. Every start rotates the capability so a previously shared read-only
  URL cannot silently become run-capable.
- Added UI controls to start or stop the private gateway. A public HTTPS base
  can be entered to copy the complete secret endpoint for ChatGPT. The app says
  explicitly that the local listener is not internet-accessible and that a
  trusted tunnel or hosted relay remains necessary.
- Added integration and UI security tests, packaged-resource assertions, user
  documentation and MCP bridge version 2.

## Results

no measurements — implementation only

| Condition | n | Metric | Value |
|---|---:|---|---:|
| MCP integration suite | 11 tests | passed | 11/11 |
| AI integration UI/security contract | 1 script | result | passed |
| Swift debug build | 1 build | result | passed |

The remote test starts a real loopback gateway, rejects a request with the wrong
capability path, lists only read tools under the read profile, confirms the run
profile contains scientific `job_start` but no engine-administration tool, and
then terminates the complete gateway process group.

## Decision and rationale

Desktop client registration belongs in iProteinStudio's UI, with explicit
consent and read-only as the initial choice. The underlying configuration
utility remains valuable for automation and recovery, but it is not part of the
normal product journey.

Remote access remains a separate, explicit switch. Automatically binding a
scientific execution service to the LAN or public internet was rejected: local
MCP configuration is not network authorization, and a user downloading a
protein-design app has not consented to making its tools remotely reachable.
The gateway therefore starts on loopback, carries no administration capability,
uses a revocable secret and leaves HTTPS publication to a separately chosen
provider.

The capability URL supports clients whose custom MCP setup has a no-auth mode,
but it is still a credential. It was chosen as an interoperable local boundary,
not as a replacement for a first-party account-authenticated relay. A hosted
iProteinStudio relay would be the cleanest general-user experience, but it
requires an operated service, user accounts, authentication, abuse controls and
a privacy policy; none can be silently created from a local repository change.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
/usr/bin/python3 Tests/test_mcp_bridge.py
bash Tests/test_ai_integrations_ui_contract.sh
swift build

# Developer diagnostics; normal users use the AI settings screen.
/usr/bin/python3 Sources/iProteinStudio/Resources/pipeline/mcp/studioctl.py doctor
/usr/bin/python3 Sources/iProteinStudio/Resources/pipeline/mcp/remote_gateway.py status
```

## Limits and what was not tested

- No personal Codex, Claude Desktop or Claude Code configuration was changed in
  this entry. The writers were tested against isolated configurations, including
  unrelated entries, status, access updates and scoped removal.
- Codex and Claude Desktop were not installed as standalone applications in
  `/Applications` on this Mac. The generated Codex configuration had previously
  been accepted by an installed Codex client; Claude Desktop's exact JSON shape
  is regression-tested but needs acceptance on an installed release.
- There was no public HTTPS endpoint, tunnel binary, hosted relay, OAuth
  provider or ChatGPT custom app available. Consequently no end-to-end ChatGPT
  desktop/phone tool call was claimed or tested.
- A capability-bearing URL can be captured by a reverse proxy's access logs.
  The proxy must suppress paths and provide TLS, rate limiting and appropriate
  operational controls. For a general public release, account-based OAuth is
  preferable.
- The gateway keeps an awake Mac reachable; it cannot make a powered-off Mac
  available and does not configure Wake-on-LAN or a tunnel provider.
- No model inference or performance measurement was repeated. Remote scientific
  jobs still use the tested broker and existing model runners.

## Next

Choose the public-access model: a first-party authenticated iProteinStudio relay
for general users, or an explicitly supported tunnel provider for advanced
users. Then validate a real ChatGPT custom app from iPhone and an installed
Claude Desktop release before advertising either as end-to-end supported.
