---
entry: 0264
title: Plan a native introduction to Studio and prototype three directions
date: 2026-10-02
author: Codex
type: decision
status: complete
machine: local macOS host; browser previews and hosted image generation
tags: [ui, onboarding, design, artwork, planning]
---

## Context

The user requested an introduction to the app and its capabilities that feels
native to macOS: clean, descriptive, capable and respectful. They explicitly
requested planning and explanations, with optional artwork and multiple
prototypes, rather than an app update. The earlier no-GPU-work constraint remains.

## What was done

Reviewed the current `RootView`/`SetupView` installation-first routing and the
workspace's sidebar/toolbar vocabulary. Consulted Apple's primary Human Interface
Guidelines for onboarding, macOS and toolbars. No application files were edited.

Created [the design plan](../docs/ONBOARDING_CONCEPTS.md), explaining three options,
the proposed first-launch sequence, copy, native behavior, accessibility,
installation/recovery boundaries, art direction and an evaluation plan.

Created interactive concepts for:

- **A — Welcome window:** compact identity, project/sample/capability actions and
  a discoverable first-design lesson entry. Capability exploration is separate
  from project setup.
- **B — Optional introduction:** three screens explaining the experiment, method
  comparisons/candidate records and local execution/explicit online connections.
- **C — Learn in a project:** sample route with selectable stage explanations,
  plus dismissible and reopenable inspector guidance.

The canonical conversation fragment is in this thread's visualization directory;
a duplicate source and standalone review previews are in
`artifacts/0264-native-onboarding/`. No API calls, installations, file access to
scientific inputs or job execution are available from the concepts.

Generated one original transparent raster artwork, **Fold and possibility**,
using built-in hosted image_gen. Saved the original, unmodified PNG and exact
prompt in the artifact directory. The abstract ribbon/branches represent an art
direction, not molecular structure or experimental evidence. Incorporated the
same PNG into the Welcome concept without image processing or resampling.

## Results

No performance measurements — planning, visual review and interaction checks only.

| Check | Outcome |
|---|---|
| Welcome | New-project goal selection, requirements preview and return to Welcome exercised |
| Capability exploration | Catalogue descriptions open without an install action; explicit Create Project moves to goal configuration |
| Tour | Three pages, completion, replay and skip exercised |
| Project guide | Stage explanation, sequential tips, dismissal and reopening exercised |
| Dark/light review | Welcome inspected and captured in both appearances; light preview uses an inspection-only override |
| Narrow review | Welcome and project variants reported 388-pixel content at a 388-pixel container width; no horizontal overflow observed |
| Browser errors | No console errors returned during the checked interactions |
| Artifact integrity | Canonical fragment remains below the 1 MB visualization limit; source copies match; PNG is 1499 × 1049 with RGBA color type |

Evidence includes `welcome-light.png`, `welcome-dark.png`,
`project-guide-dark.png`, `fold-and-possibility.png`, `artwork-prompt.txt`,
`studio-introduction.fragment.html`, `preview.html`, `preview-light.html` and
`checks.json` in the artifact directory. The local preview server serves only
this static concept directory on loopback. The initial sandbox-blocked socket
bind was retried with authorized escalation.

## Decision and rationale

Recommend A as the entry and C as the optional teaching layer; keep B available
from Help/Discover Studio. This gives experienced users direct project access
and gives new users a meaningful task before unfamiliar engine/download choices.
It follows Apple's emphasis on optional onboarding and contextual explanation.

Retain the existing first-design tabletop as a separate learning experience.
Do not gamify ordinary scientific results or make lesson completion authorize
downloads or inference. Use native system controls and typography in eventual
implementation; the browser window chrome and stand-in glyphs express layout
intent, not production AppKit/SF Symbol assets.

Artwork belongs on the Welcome surface only. Its quiet material and silhouette
add identity without crowding the actions or implying a validated protein. The
prototype also supports an optional host control to remove it.

## Reproduce

Open the standalone preview, or from the repository root run:

```bash
python3 -m http.server 8769 --bind 127.0.0.1 \
  --directory lab_book/artifacts/0264-native-onboarding
```

Inspect `http://127.0.0.1:8769/preview.html`; use the variant picker below the
window to switch A/B/C. The light-appearance inspection fixture is
`preview-light.html`. The self-contained previews require no model engines.

Regenerate the artwork with the saved prompt using built-in image_gen and
`transparent_background=true`. Image generation is not deterministic; the saved
PNG is the authoritative concept asset.

## Limits and what was not tested

No application update, native implementation, installation, engine detection,
scientific GPU job, benchmark mutation, project migration, external assistant
registration or scientific result. No native VoiceOver/keyboard audit, translation
review, measured learning/retention/enjoyment benefit or participant study. The
mockup's requirement lists are explanatory, not complete dependency/install plans.
Candidate assay references are proposed record content, not a claim of an
existing experimental-data subsystem. A production sample needs real curated,
provenance-linked artifacts. No Swift build was needed or run for this design-only
pass; no commit was made.

## Next

Review A plus C with the user. Test the concept with bench scientists and
experienced designers before native implementation. Preserve installer review,
partial completion/recovery, storage failure priority and all normal scientific
planning/execution safeguards when moving orientation ahead of installation.
