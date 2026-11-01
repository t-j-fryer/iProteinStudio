---
entry: 0679
title: Repair shared design configuration for the public release and beta
date: 2026-11-01
author: Codex
type: implementation
status: complete
machine: Apple silicon development Mac; existing pinned RFD4 CPU runtime; no GPU inference
tags: [rfd4, ui, public-release, nanobody, configuration]
---

## Context

The user reported unlabeled populated RFD4 controls, an unexplained Metal-kernel
option, a single exposed framework, missing sequence target preparation, fixed
campaign lengths, missing hit filters and a restricted predictor menu. They
clarified that the changes belong in the public app and all versions, not only
beta. Work started on 2026-10-31 and completed on 2026-11-01.

## What was done

Implemented in the local `release/paper-next` candidate, then applied the shared
patch to the canonical `beta/development` checkout. Preserved beta-only result
adapters and unrelated dirty work. No commit, public push, release upload, appcast
change or installed stable-app replacement was performed.

- Added persistent field labels and explanatory copy to RFD4, shared run naming,
  relevant RFD3 controls, Protein Hunter/custom design and NISE. `0.1` is sequence
  sampling temperature; `C` is cysteine exclusion; `42` is the generation seed;
  A/B are output chain roles.
- Explained optimized Metal pair operations and exact reference checking. Default
  remains off. A varied-length generation stage checks its first sample at each
  distinct length; timed child stages retain their existing first-sample check.
- Exposed the existing managed target-preparation service in the detailed RFD4
  form, with protein sequences/assemblies, cache reuse and explicit readiness.
- Bundled the other seven existing apo framework structures. Verified each against
  its prior completion checksum, exact catalogue sequence and contiguous residue
  positions. These contain no target coordinates or model weights. All eight use
  catalogue-specific CDR boundaries; overrides are explicit. 3EAK’s heuristic CDR
  provenance remains visible. Missing framework MSAs use the existing explicit
  automatic cache/server resolver, not a single-sequence fallback.
- Added frozen equal-length allocation and custom counts. Each distinct length is
  authored/audited separately during preflight; family seeds and length assignments
  survive budget subdivision and resume. Generation keeps one resident model.
- Added family-grouped ESMFold2, Boltz, IntelliFold, Protenix and OpenFold choices.
  New choices reuse the existing resident adapters, exact runtime mapping and
  engine-specific environment. Each sequence proposal receives one sample.
- Added conjunctive protein hit gates for ipSAE(min), iPTM and mean complex pLDDT.
  Gates label saved candidates, fail closed on missing metrics, and do not prune
  outputs or alter search selection. The results browser reads saved verdicts.
- Updated the MCP schema, shared backend validation and public RFD4 guide.

## Tests and results

No performance measurements — implementation only.

- `swift build` passed in both public candidate and beta checkouts.
- Public candidate local app packaging passed (ad-hoc signed, updates disabled).
- 19 existing/new backend contract tests passed; the expanded configuration suite
  then passed all 8 tests including mixed-entity rejection and automatic catalogue
  CDR assignment. The suites overlap; these are not 27 distinct tests.
- Native CPU authoring and feature preparation passed for all 8 frameworks and
  three protein-binder lengths (75/76/77 aa), using isolated test asset views.
- Swift recommended-workflow, RFD4 configuration and result-loading harnesses
  passed, including legacy JSON decoding, saved hit verdicts, lineage identities
  and tampered-coordinate rejection.
- `git diff --check` passed. The public patch contains no private peptide workflow,
  manuscript results, model weights or changes to installed runtimes.

An initial broad Python discovery omitted `NANOHUNTER_ROOT` required by the native
input tests. Focused contracts and correctly configured native-input tests were
subsequently run successfully. Swift build cache writes required explicit writable
module caches; local app packaging used the standard build script with approval.

## Reproduce

From either checkout (the release candidate is `.worktrees/paper-release`):

```bash
CLANG_MODULE_CACHE_PATH=/tmp/studio-config-clang \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/studio-config-swift \
swift build --disable-sandbox --cache-path /tmp/studio-config-spm
STUDIO_SWIFT_CASES=recommended_workflows,rfd4_configuration,results \
python3 Tests/run_swift_contracts.py
PYTHONPATH=tools:Tests PYTHONDONTWRITEBYTECODE=1 \
"$NANOHUNTER_ROOT/venvs/NanoHunter_rfd4/bin/python" -B -m unittest \
  test_rfd4 test_rfd4_configuration test_rfd4_native test_rfd4_multichain
"$NANOHUNTER_ROOT/venvs/NanoHunter_rfd4/bin/python" -B -m unittest discover \
  -s Tests -p test_rfd4_configuration_inputs.py
```

The last command requires `NANOHUNTER_ROOT` exported to the existing installed
runtime. It runs CPU input preparation only, not a campaign.

## Limits and remaining release work

- No inference campaign or GPU smoke was launched. Expanded predictor/framework
  combinations still need end-to-end qualification before a public binary release.
  CPU feature validity is not evidence of binding or model-output quality.
- Mixed protein–ligand target refinement is **not implemented**. The former protein
  path silently discarded non-protein entities; it now rejects them. Prediction
  and dedicated small-molecule design remain available, as does native annotated
  input. Preserving ligand context throughout generation, sequence design and
  reprediction requires a separate implementation and validation.
- A full native form visual review was not completed. The terminal-launched
  temporary review app aborted (exit 134); computer-use opened a separate review
  copy without the intended temporary environment. It showed the normal workspace
  list, was inspected read-only and closed. No design was started or edited.
- The installed stable app, queue entries, active jobs, frozen settings and raw
  scientific outputs were not changed. Candidate files are local only.
