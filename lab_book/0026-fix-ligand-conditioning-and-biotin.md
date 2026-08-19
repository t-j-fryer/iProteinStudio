---
entry: 0026
title: Make ligand conditioning explicit, mapped, and stereochemistry-safe
date: 2026-08-18
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, ligand, ui, pdb, testing]
---

## Context

The audit in [[0025-audit-ligand-conditioning-and-biotin]] found that RFdiffusion3's
**Suggest for me** button guessed from generic exposure SMARTS, the drawing showed
zero-based SMILES indices while the condition table used unrelated canonical RFD3
names, one attachment atom could not identify a linker branch, donor/acceptor text
was reversed relative to Foundry, and biotin's exact PDB component was skipped after
the search accepted a different stereoisomer first.

Those were not cosmetic defects. Each could produce a plausible completed campaign
with a pocket conditioned on the wrong atoms or a misleading claim that no
experimental structure existed.

## What was done

`inspect_target.py` now reproduces RFD3's hydrogen-added canonical ranking and emits
the original SMILES atom index beside each exact RFD atom name. RDKit's validated
Lipinski feature definitions supply donor and acceptor roles for the graph actually
submitted. Automatic burial is deliberately narrower: only neutral carbon or halogen
core atoms are proposed, so a charged atom that happens not to be a donor or acceptor
is not mislabeled non-polar. Hotspots are never guessed.

The molecule picker now labels every atom, shows zero-based indices before target
inspection and exact RFD names afterward, and represents a conjugation point as a
directed acyclic bond. The first click is the recognition-core endpoint and the
second must be its directly bonded linker-side neighbour. The analysis cuts that
bond and proves the two resulting regions; ring bonds, non-neighbours and one-ended
legacy selections fail visibly. Both RFdiffusion3 and iterative ligand forms use the
same picker and cross-check the clicked elements at the Python boundary.

The picker also gained an explicit WebAssembly-ready handshake. Previously the HTML
document could finish before RDKit initialised, causing initial labels, selection and
read-only state to be dropped until a later SwiftUI refresh. Process wrappers for the
target inspector, ligand analysis and Boltz atom resolver now invalidate stale
callbacks when input changes or a job is cancelled.

The conditioning form now explains Foundry's target-atom semantics, shows both the
index and the RFD name, and previews suggestion counts and rationale before replacing
any existing choices. Changing the directed linker bond clears the old proposal and
conditions because an atom that was core under the old cut may be linker under the
new one. Explicit linker-side atoms are proposed exposed; RDKit donor/acceptor roles
are proposed on the core; hotspots remain a deliberate user choice.

Conjugation intent is persisted separately from the two endpoints. This closes the
short but real unsafe state between enabling “attached” and completing the second
click: both RFdiffusion3 and iterative Start buttons remain blocked until the directed
bond is complete, and older one-ended projects migrate into that visible incomplete
state instead of being treated as free ligands.

RCSB graph-search candidates are now checked by the complete InChIKey, including
stereochemistry and protonation. Every exact CCD code is searched, entry IDs are
deduplicated globally, and retrieval continues past an empty or mismatched first
candidate. Retrieved structures that do not match a computed state are counted
separately rather than forced into the nearest cluster.

The request models, examples, serialisation contracts and CLI documentation were
updated for the two attachment endpoints and corrected hydrogen-bond direction.

## Results

No performance benchmark was made; this was correctness and UI acceptance work.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Ligand Python contract suite | 5 tests | naming, chemistry, directed split, exact CCD, YAML direction | pass |
| Exact submitted biotin, live RCSB | 1 search capped at 100 entries | exact CCD codes | `BTN` only |
| Exact submitted biotin, live RCSB | 100 entries | coordinates retrieved / matched / unmatched | 98 / 75 / 23 |
| Real WKWebView, submitted biotin | 1 render | heavy atoms / bonds / labels / selected endpoint rings | 16 / 17 / 16 / 2, pass |
| Live release GUI, fluorescein example | 31 heavy atoms | suggested bury / donor / acceptor / hotspot | 23 / 2 / 7 / 0 |
| Workflow Python suite | 1 suite | predict/RFD3 input and output contracts | pass |
| Iterative shell suite | 1 suite | CLI lowering and validation | pass |
| Swift production-source harnesses | 2 suites | RFdiffusion3/Predict and iterative request contracts | pass |
| Managed component detection | 9 components | usable | 9 |
| Debug build + release bundle + strict signature check | 1 each | result | pass |

The live app pass moved RFdiffusion3 from protein to ligand, read the target, opened
and cancelled the suggestion preview, navigated to Predict, then restored the original
alpha-cobratoxin target and B67/B69/B71 hotspots. The RFdiffusion3 navigation rail,
form scrollbar and Start control remained accessible throughout.

## Decision and rationale

**Use a directed bond, not a guessed branch.** A single attachment atom has multiple
possible outgoing branches. Choosing the largest or most heteroatom-rich branch had
already mislabeled the biotin recognition core. Two adjacent user-picked endpoints
express the intended topology without an unreliable chemical guess.

**Automate feature perception, not scientific intent.** RDKit can reliably identify
donor/acceptor roles for the supplied tautomer and protonation; it cannot decide which
face the experimenter wants contacted. Therefore donor/acceptor and conservative
hydrophobic burial are proposed, while hotspots are not.

**Require complete chemical identity for experimental evidence.** Connectivity-only
matching conflated biotin with stereoisomers. The full InChIKey is stricter and may
exclude differently protonated deposited components, which is intentional because
those can change both conformation and hydrogen-bond roles.

**Preview rather than silently apply.** Even chemically valid suggestions are design
choices. Showing the exact counts and rule before replacement makes the automation
legible and reversible.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_ligand_conditioning.py
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py
caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /private/tmp/iproteinstudio-workflow-contract
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract

caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Sources/iProteinStudio/Resources/rfd3/ligand_intelligence.py \
  /private/tmp/iproteinstudio-biotin-fixed-request.json

caffeinate -dimsu /private/tmp/iproteinstudio-ligand-picker-harness

env SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift-cache \
  caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

The live request used exactly:
`C1[C@H]2[C@@H]([C@@H](S1)CCCCC(=O)O)NC(=O)N2`, with PDB search on and
`max_pdb_entries=100`.

## Limits and what was not tested

- RCSB counts are live external data and will change as entries are added or revised.
- The exact-identity acceptance used biotin in its submitted neutral tautomer. Other
  salts, isotopes, covalent adducts and metal-containing ligands were not sampled.
- Donor/acceptor perception is reliable for the molecular graph supplied; Studio does
  not infer the biologically dominant protonation or tautomer.
- The RFdiffusion3 network's quantitative adherence to each condition was not newly
  benchmarked. The emitted feature direction was checked against the pinned
  Foundry contract and the YAML output.
- No GPU model was rerun because these changes stop at request preparation and the
  molecule UI. The installed-method GPU/CPU matrix remains the acceptance recorded in
  [[0024-editable-numbers-richardson-and-method-matrix]].
- The GUI pass used light appearance and the current display scale, not a full
  VoiceOver, keyboard-only, dark-mode or increased-contrast audit.
- This machine's default Command Line Tools currently combine Swift 6.3.3 with an
  incompatible macOS 26.5 SDK module build. The checked build pins the installed 15.4
  SDK; the release script also completed successfully from the existing build tree.

## Next

Check in the real WebKit harness as a supported UI-test target, then add a small
curated ligand matrix covering charged, zwitterionic, aromatic-nitrogen,
metal-coordinating and covalently attached examples.
