---
entry: 0059
title: Make prediction MSA failures retryable and diagnosable
date: 2026-09-01
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, macOS
tags: [prediction, msa, colabfold, protenix, reliability, diagnostics]
---

## Context

The first external DMG installation reached prediction but stopped with “The
MSA server could not be reached.” That message came only from plain Predict's
shared batch driver. It represented every failure—missing client, TLS, DNS,
rate limiting, server errors, an invalid response, or an alignment with no
homologues—as the same network outage and did not tell the user where its
already-written log lived. Unlike iterative design, plain Predict made only one
attempt.

## What was done

- Exercised `https://api.colabfold.com` through both the managed Boltz and
  Protenix clients, including real ubiquitin MSA submissions.
- Kept provider selection deterministic: a prediction set containing Protenix
  continues to use Protenix's native upstream MSA command; other sets use
  Boltz's ColabFold client. There is no silent cross-provider fallback.
- Added three bounded attempts with 5- and 10-second outer backoff to both
  branches of plain Predict's MSA generation.
- After build 6 exposed the external Mac's real error, traced it to the pinned
  Boltz client accepting the presence of `out.tar.gz` as proof of a completed
  download without checking HTTP status or archive integrity. A truncated or
  non-archive response was therefore reopened on every retry. Boltz attempts
  now use distinct clean output directories, so no failed archive is reusable.
- Preserved the complete failed-attempt log under the shared MSA cache.
- Extracted the final useful TLS/DNS/HTTP/service cause from progress-heavy
  upstream logs and included it, the provider, and the full log path in the GUI
  failure.
- Retained the fail-loud scientific boundary: failure never changes `msa: auto`
  into an unaligned prediction.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Host HTTPS probe to ColabFold | 1 | HTTP response | 404 at root (reachable) |
| Managed Boltz MSA client, ubiquitin | 1 | completed server job | yes |
| Patched plain-Predict Boltz route, ubiquitin | 1 | valid cached A3M / elapsed | yes / 30.0 s |
| Managed Protenix MSA client, ubiquitin | 1 | homologues written | 20,078 |
| Synthetic transient failures | 1 | accepted attempt | 3 of 3 |
| Synthetic persistent timeout | 1 | attempts/log retained | 3 / yes |
| Synthetic corrupt Boltz archive then valid response | 1 | clean second attempt | yes |

The homologue count is a service response observed during diagnosis, not a
performance benchmark or a guaranteed future result.

## Decision and rationale

Studio retries the selected provider rather than switching providers. A silent
switch would make the same saved prediction settings produce different
scientific inputs depending on which engines happened to be installed. It also
continues to stop rather than infer without an alignment: the scientist can
explicitly choose single-sequence mode, but a network failure cannot make that
choice for them.

The `a3m.mmseqs.com` hostname was not adopted as a fallback because it currently
redirects to the same `api.colabfold.com` service; it is not an independent
availability path.

## Reproduce

```bash
python3 -m unittest Tests/test_prediction_msa_reliability.py
```

The live probes used the installed managed clients and a ubiquitin sequence.
They intentionally are not part of the ordinary offline test suite because the
public service is external and rate limited.

## Limits and what was not tested

- The external Mac's full log was not locally available, but build 6 surfaced
  its tar reader failure and established that the downloaded payload was not a
  complete archive. Why the public endpoint returned that payload remains
  external to Studio.
- A full structure prediction was not needed to validate the MSA stage.
- No claim is made that the public service is continuously available.
- The isolated-download retry still needs one acceptance run from build 7 on
  the external Mac.

## Next

Install build 7 on the external Mac and repeat the prediction. If all three
attempts fail, use the path shown in the error to inspect or share the exact MSA
log; no additional reproduction steps are required.
