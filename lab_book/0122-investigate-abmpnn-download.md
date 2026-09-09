---
entry: 0122
title: Investigate the AbMPNN connection failure
date: 2026-09-09
author: Codex
type: audit
status: complete
machine: local Apple Silicon development Mac
tags: [install, downloads, diagnosis]
---

## Context

A user reported a connection error downloading AbMPNN and supplied
`setup-1788986582-1BA80A39.log`. Investigate the configured endpoint and what the
log establishes without changing scientific assets or the running installation.

## What was done

Read the supplied setup log and the installer/downloader source. Inspected a
previous successful setup log. Made bounded HEAD, byte-range GET and API metadata
requests to the configured public Zenodo record. No weights were downloaded,
changed, committed or redistributed, and no engine installation was launched.

## Results

No performance benchmark — connectivity diagnostics only.

- Supplied log: Boltz setup completed; ProteinMPNN, SolubleMPNN and LigandMPNN
  checkpoints were already present. AbMPNN retried from **0 B**, reaching attempt
  3/20. The file ends there, before the downloader's final exception.
- Configured URL:
  `https://zenodo.org/records/8164693/files/abmpnn.pt?download=1`.
  The expected SHA-256 remains
  `fd41b40ee0f51974d73e1acb754cd8acaa36b3327543d5d28bcf4aa4e07b4a1b`.
- A HEAD request to that URL received HTTP **504 Gateway Time-out**.
- A HEAD request to Zenodo's API file-content route timed out after 20 seconds
  with no received bytes. Separate bounded GETs to the checkpoint and record API
  completed TCP/TLS connection but received no response bytes within 15 seconds.
- An earlier local setup log (`setup-1788296727-26F74BFF.log`) records the same
  AbMPNN checkpoint successfully downloading approximately 20 MB and completing
  the MPNN component installation.
- Existing downloader behavior: 20 attempts, 30-second socket timeout, retry
  backoff and retention of partial files. Completed checkpoints are reused after
  checksum verification. Setup does not mark MPNN complete without AbMPNN.

The evidence is consistent with a Zenodo service/access-path problem. It does not
prove a global Zenodo outage or establish the exact exception on the other Mac.
Current retry progress messages omit the immediate exception, making truncated
logs less diagnostic. No alternative checkpoint or unverified mirror was substituted.

## Decision and rationale

Recommend retrying the existing setup after connectivity recovers. Keep the pinned
checkpoint and integrity verification. A source-code or model replacement is not
supported by this evidence. Diagnose the final exception if failures persist;
transport, certificate and HTTP errors should not be conflated.

## Reproduce

```bash
curl -I -L --connect-timeout 15 --max-time 40 'https://zenodo.org/records/8164693/files/abmpnn.pt?download=1'
curl -sS -I --connect-timeout 10 --max-time 20 'https://zenodo.org/api/records/8164693/files/abmpnn.pt/content'
curl -sS --range 0-1023 --output /dev/null --connect-timeout 8 --max-time 15 --write-out 'HTTP=%{http_code} connect=%{time_connect} TLS=%{time_appconnect} total=%{time_total}\n' 'https://zenodo.org/records/8164693/files/abmpnn.pt?download=1'
curl -sS --output /dev/null --connect-timeout 8 --max-time 15 --write-out 'HTTP=%{http_code} connect=%{time_connect} TLS=%{time_appconnect} total=%{time_total}\n' 'https://zenodo.org/api/records/8164693'
```

## Limits and what was not tested

No live request from the affected Mac, complete failing log, alternate network,
successful fresh AbMPNN transfer or whole installation was available. A gateway
or access-path failure observed here cannot identify the originating service or
prove the same error on another network. No application code changed; build and
model tests were not repeated for this read-only investigation.

## Next

Retry once Zenodo is reachable. If failures persist, inspect the complete final
exception. Improve per-attempt error reporting in a future downloader change so
the first retry includes actionable HTTP/TLS/timeout context.
