---
entry: 0212
title: Add live Mac resource readings to job progress
date: 2026-09-28
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory; macOS developer machine
tags: [ui, monitoring, support]
---

## Context

Following the student calibration/supervision audit in entry 0210, the user requested live RAM and GPU reporting inside the app so students need not use Activity Monitor.

## What was done

Added `StudioCore/SystemResourceSnapshot.swift`, native read-only Mach/sysctl/IORegistry collection and explicitly optional counters. Added `Core/ResourceUsageMonitor.swift` with bounded in-memory history and `Views/ResourceUsageView.swift`. The shared Job progress window displays the panel for all workflows and includes the history in Copy support report. Polling is independent of broker polling and off the main actor; no helper processes or elevated privileges are requested by the app. Documented semantics and limitations in `docs/LIVE_RESOURCES.md`.

## Results

`swift build` passed. Five SystemResourceTests passed, covering RAM accounting, missing/invalid counters, CPU resets, swap traffic and a live native read. A three-sample native SwiftUI smoke test exercised CPU deltas, support history and rendered the panel to `build/resource-monitor-smoke/panel.png`. Live collection returned Normal pressure, readable swap and a GPU percentage on this Mac. This is a functional test, not a throughput benchmark; no monitoring overhead claim is made.

## Decision and rationale

Show whole-Mac usage, explicitly not per-job GPU attribution. Use memory pressure and swap writes alongside RAM because high occupancy or allocated swap alone does not establish thrashing. Driver GPU counters are best effort; nil is Unavailable, never zero. Cap history at 150 samples and stop collecting when the window closes. Avoid privileged powermetrics, shell process polling, and conflating the frontend's Metal allocations with workers' usage.

## Reproduce

`swift build`

`swift test --filter SystemResourceTests`

The ignored `build/resource-monitor-smoke/Smoke.swift` captures three real samples, verifies support history and renders the actual panel sources in isolation. Build/test logs are in `build/student-debug-20260928/resource-{build,tests}.log`.

## Limits and what was not tested

Not tested on the student's M4 Pro/24 GB, other Apple GPU generations, multi-GPU Macs, under forced memory pressure, or during a long-running design. Counter failure and reset handling tested with deterministic inputs. No benchmark, source commit, packaged app replacement, DMG or GitHub release. Existing broker process-inspection timeout remains a separate known issue. History is only retained while the progress window exists; this is not an always-on campaign resource trace.

## Next

Qualify on the student's hardware and ship with the separately needed supervisor-timeout fix. Do not infer per-job resource usage or model progress from system-wide counters.

## Release integration

Shipped in 0.2.11/build57 with MCP32 and the supervisor fix; see [0213](0213-fix-process-inspection-supervision.md) for publication, app replacement and shared-runtime verification. The earlier limits above describe the initial implementation pass.
