---
entry: 0270
title: Group workspace navigation into Predict and Design
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: local macOS host; hosted image generation
tags: [ui, navigation, branding]
---

## Context

Following [[0268-adopt-natural-app-identity]], the user requested two main tabs:
Predict and Design, with Protein Hunter, NISE and RFdiffusion3 selected inside
Design. They requested the website's Design/Predict symbols and a revised
Protein Hunter icon representing independent branching trajectories.

## What was done

Replaced the four-way workspace picker in `Views/RootView.swift` with labelled
Predict and Design controls. Predict opens its existing workflow. Design opens
`DesignMethodChooser`, with three explicit method choices. Clicking Design again
or the Design methods back control reopens the chooser. The last persisted
workflow is unchanged until an actual method is selected; original mode raw
values and saved project schemas remain unchanged.

The current workflow view stays mounted beneath the chooser, disabled and hidden
from pointer/accessibility interaction. Opening and closing the chooser therefore
does not discard transient form state. Choosing another method uses the existing
workflow router and saved requests. Navigation does not call job start, reset,
or engine installation. Existing run/result and queue behavior remains intact.

Added website-derived transparent Design sprout and Predict folded-shape symbols
using built-in image_gen. SwiftUI renders these as templates for light/dark
contrast. Updated Predict artwork in headers, the introduction, and workspace
entry. Generated a new Protein Hunter illustration: three physically separate
moss, terracotta and limestone trees, each with its own seed and branching buds.
No crossover, shared roots, or connections between trees. Original app-icon
artwork and old concept assets are retained.

Source PNGs and exact generation prompts are in
`Sources/iProteinStudio/Resources/Brand/NAVIGATION-PROVENANCE.txt` and adjacent
`design-glyph.png`, `predict-glyph.png`, and `hunter-trajectories.png`.
The website itself was not edited; it supplies the visual references.

## Results

No measurements — UI implementation only.

- `swift build` passed.
- `bash build_app.sh debug` assembled the local app and passed strict recursive
  code-signature verification.
- Loaded all three PNGs with Pillow, verified square dimensions, RGBA channels,
  alpha extrema 0/255, and exact equality between source and bundled images.
- Visually inspected generated assets. The Hunter metaphor has three distinct
  roots and separated branching structures; symbols match the website family.
- `git diff --check` passed.

## Decision and rationale

A two-level hierarchy separates prediction from the choice of design method.
The Design chooser is a navigable workspace surface rather than a hidden popup;
short descriptions make method selection meaningful. The actual scientific
workflow identifiers remain stable to avoid migrating saved projects.
Keep the underlying form mounted while the chooser is shown so browsing
navigation does not throw away a partially edited field.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
swift build
bash build_app.sh debug
```

Open the local build, select a workspace, and use Predict or Design. In Design,
select one of the three methods; use Design methods or the Design tab to return.
Check partially edited input by reopening the same method. Artwork regeneration
uses the exact prompts in the bundled provenance file and is non-deterministic.

## Limits and what was not tested

Native click-through testing could not be completed: the computer-use native
connection failed before returning a window, including after a session reset.
Thus new navigation focus, minimum-window sizing, VoiceOver, and transient-state
preservation have source-level review but no successful UI verification in this
turn. Build success is not claimed as a UI test. No scientific jobs, benchmarks,
engine downloads, saved real-project mutations, release publication, or installed
application replacement were performed. Conceptual branches are not a claim of
actual molecular geometry or a visual report of a run. No new behavioral unit
tests were added for this view-only navigation change.

## Next

Review native navigation and keyboard focus when the native testing connection
is restored. Refine small-size artwork if needed after user review.

## Delivery

Updated local app: `build/iProteinStudio.app`. No commit or version bump.
Unrelated existing work was preserved.
