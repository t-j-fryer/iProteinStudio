---
entry: 0271
title: Use the sculptural Design and Predict icons
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: local macOS host; hosted image generation
tags: [ui, branding]
---

## Context

Following [[0270-group-predict-and-design-navigation]], the user clarified that
the actual 3D objects above the website's Design and Predict labels should be
the app icons, rather than their flat glyph counterparts.

## What was done

Generated faithful transparent derivatives of the original natural-workflow
board using built-in imagegen. Design uses the terracotta branching trunk with
an olive ribbon; Predict uses the folded green loop inside a cream outline.
Source PNGs and exact prompts are stored in `Resources/Brand/design-object.png`,
`predict-object.png`, and `OBJECT-PROVENANCE.txt` under `Sources/iProteinStudio`.

Updated `StudioSectionTab` to render full-colour artwork at 34 points; updated
the Design chooser heading to a 68-point sculpture. The shared Predict artwork
now uses the 3D object across headers, introduction and empty workspace surfaces.
Retained navigation behavior, the Terra Loop application icon, and independent
ProteinHunter trajectory artwork. Built the local app bundle.

## Results

No measurements — implementation only.

- Visually inspected both generated objects against the original artwork.
- `swift build` passed; `bash build_app.sh debug` passed, including strict
  recursive code-signature verification.
- Pillow loaded both PNGs, confirmed RGBA and alpha extrema 0/255, and verified
  byte-identical copies inside the app bundle.
- `git diff --check` passed.

## Decision and rationale

Use the sculptures in original colours instead of tinting flat glyphs. The
materials and silhouettes are the visual identity the user explicitly selected.
Slightly larger tab artwork gives the shapes more room while retaining labels
and existing selected-state outlines.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
swift build
bash build_app.sh debug
```

Open `build/iProteinStudio.app` and inspect Predict and Design in the workspace.
Exact image-edit prompts and reference path are in `OBJECT-PROVENANCE.txt`;
regeneration is non-deterministic.

## Limits and what was not tested

Native click-through and light/dark small-size visual review remain unverified:
the native computer-use connection failed during the preceding navigation work.
Build and asset checks are not substitutes for that UI review. No scientific
jobs or performance benchmarks were run, and no new behavioral tests were
added for this asset/display-only change. No installed app replacement,
release publication, version bump, or commit was performed.

## Next

Review the full-colour artwork at native display sizes when UI access returns.
