---
entry: 0130
title: Fix atom controls and add names to all run types
date: 2026-09-09
author: GPT-6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, ligand, queue, recovery]
---

## Context

After build 36, the user reported that NISE's None/Bind/Expose controls did not
respond and requested optional run names next to Start/Add to Queue in all modes.
No scientific campaign or model behavior was requested or changed.

## What was done

- Reproduced the NISE bug with the actual SwiftUI segmented control hosted in an
  isolated native window, pre-resolved ethanol atoms, and the real bundled
  RDKit/WebKit renderer. Atom order was verified and controls were enabled, but
  clicking Bind left both selection arrays empty. Multiple mutations of the
  value-type request binding in one event overwrote preceding edits.
- Commit the NISE selection and its atom-map metadata together. Apply the same
  correction to Protein Hunter contact toggles/reset and paired linker endpoints
  in Protein Hunter/RFdiffusion3. RFdiffusion3's condition toggles already commit
  one locally assembled set. Keep all atom identity and stale-map guards.
- Move highlight circles above RDKit's opaque background rectangle and below
  its bonds. Previously the background concealed the highlights. Clarify the
  green Bind/orange Expose legend and use neutral atom-name wording in the
  shared viewer.
- Add per-workflow draft run names to saved workspaces with backward-compatible
  decoding. Add a Run name field beside all four launch buttons. Each new run
  freezes a normalized human label in `studio_run_label.json`; names are not
  paths, shell arguments or resume identifiers. Existing unique directories
  remain authoritative. Queue and Activity/history display the label.
- Include label metadata in desktop plan provenance and preserve it in the job
  registry, including engine batches. Duplicate labels create distinct runs.
  Empty names retain the prior automatic-name behavior.

## Results

No performance measurements — implementation only.

- The native NISE UI regression failed before the atomic binding fix and passed
  afterward. Extended checks passed for None/Bind/Expose, visible SVG shading,
  independent atoms, saved-map round-trip, stale-map disabling and clearing.
- Desktop broker suite: 16 tests passed, including names carried through all four
  native workflow plans and serialized inert jobs, and rejection of a label
  changed after preflight.
- Debug app build and all six Swift contract executables passed, including
  duplicate run names with separate outputs, normalized label persistence, and
  per-tab name migration.
- Clean-source release build passed from
  `93bc7f695e9cc2fb3782b60594e115071e2b811e`: version 0.2.0, build 37,
  arm64, ad-hoc signed. Deep/strict code-signature and packaged-resource checks,
  Sparkle archive signing, DMG verification and archive checksums passed.
  DMG: `build/unsigned-beta-0.2.0-37/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  SHA-256: `9c8f17322ad27f73d95ccf463a3bd2f3e4117de7040a316bd2e3b4fd41228fe0`.
- Quit the old app normally and opened build 37 (app PID 89440). The existing
  running job retained supervisor PID 16600 and child PID 16611; the two waiting
  jobs retained PIDs 82138 and 82576 and remained queued. No job stop/resume or
  scientific runtime update was performed.

## Decision and rationale

Fix the binding transaction rather than remove map verification or change atom
numbering. Persist run names as presentation metadata instead of reusing a user
label as a filesystem path or pipeline run identifier; this preserves existing
resume discovery, accommodates punctuation, and avoids overwriting prior runs.

## Reproduce

From the repository root:

```bash
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules bash Tests/test_ligand_atom_selection.sh
python3 Tests/test_desktop_jobs.py
python3 Tests/run_swift_contracts.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules swift build --disable-sandbox --skip-update
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules bash release/release_app.sh --unsigned-beta
hdiutil verify build/unsigned-beta-0.2.0-37/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg
```

The native fixture opens only its own window and never reads user workspace
settings or submits work. Broker/controller tests use temporary roots or mock
sessions. Before the fix, the native test printed `bind: hotspots=[], exposed=[]`
and failed its selection assertion.

## Limits and what was not tested

No real inference, model throughput, scientific binding/filter effectiveness,
fresh-Mac installation, or VoiceOver acceptance. The direct native click test
covers NISE; Protein Hunter and RFdiffusion3 receive the same atomic update
pattern but were not clicked through in a complete design form. Existing jobs
and their frozen runtime snapshots are unchanged. No rename-after-submission
feature or binary GitHub release is included. The local package is not Developer
ID signed or Apple notarized.

## Next

Broaden native UI acceptance to the complete Protein Hunter/RFdiffusion3 forms
when available. Source changes and this artifact audit are committed for the
authorized GitHub update; generated app/DMG artifacts stay outside Git.
