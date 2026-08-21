---
entry: 0029
title: Retire untrusted JAX/Metal predictors and retain IntelliFold PyTorch
date: 2026-08-20
author: codex-gpt-5
type: decision
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, ui, install, alphafold3, intellifold, jax, mps]
---

## Context

[[0028-audit-af3-apple-gpu-and-prediction-sampling]] established a controlled
same-input quality difference that was not explained by MSA routing, seeds or
recycles. AlphaFold 3 and IntelliFold JAX/Metal produced poor cobratoxin models,
while IntelliFold PyTorch/Metal produced a credible model from the same
100,798-byte, 1,148-record A3M, seed 42 and ten recycles. A diagnostic reference
run also showed that the model inputs could produce a credible result away from
the affected JAX/Metal execution path.

Keeping an engine selectable merely because it launches violates Studio's
noob-proof and reproducibility requirements. The product must not ask a user to
distinguish “installed” from “scientifically trustworthy.” The user therefore
decided to remove both affected routes, retain IntelliFold PyTorch, and not offer
CPU as an alternative.

## What was done

- Removed AlphaFold 3 and IntelliFold JAX/Metal from Predict, iterative design,
  RFdiffusion3 verification, setup choices, dependency detection and current
  predictor lists.
- Kept their serialized enum identities solely so old projects and run results
  still decode. Legacy results are labelled `retired`; legacy selections are
  filtered from prediction/checker requests, and a legacy AlphaFold 3 iterative
  driver makes that saved form non-runnable until the user explicitly chooses a
  supported engine. No replacement is selected silently.
- Added fail-loud rejection for the historical CLI predictor names and setup
  flags. This closes paths through `nanohunter_run.sh`, plain prediction,
  RFdiffusion3 campaign preparation and the predictor overlay even when a stale
  hand-written config bypasses the GUI.
- Deleted the bundled AlphaFold adapter, JAX IntelliFold wrapper, CIF repair
  helper and AF3 target-preparation wrapper. Removed their environment and
  scheduling branches.
- Replaced the former combined IntelliFold patch with a narrowly scoped
  `intellifold_pytorch_mps.patch`. It retains only upstream PyTorch changes used
  by the supported Metal path: dynamic token buckets, MPS-safe data loading and
  CUDA-only cache cleanup.
- Removed current documentation that described the retired engines as
  experimental, opt-in or installable. Historical Lab Book entries were not
  rewritten; this entry supersedes those product-state claims.
- Deliberately did not delete any existing user-supplied AlphaFold parameters,
  old environments or outputs under a managed root. New Studio code neither
  detects nor uses them. Deleting user data is not part of predictor retirement.

## Results

No new performance benchmark was run. The scientific decision uses the
same-input measurements from entry 0028:

| Condition | n | Metric | Value |
|---|---:|---|---:|
| IntelliFold PyTorch v2-flash / MPS | 1 | pTM | 0.719 |
| IntelliFold PyTorch v2-flash / MPS | 1 | mean pLDDT | 89.8 |
| IntelliFold JAX v2-flash / MPS, best existing sample | 5 | best pTM | 0.34 |
| AlphaFold 3 v3.0.4 / JAX-MPS | 1 | pTM | 0.31 |
| AlphaFold 3 v3.0.4 / JAX-MPS | 1 | mean pLDDT | 43.0 |

Implementation acceptance results are recorded below after running the commands
in Reproduce. These are pass/fail checks, not performance claims.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Swift request/result + shell/Python workflow contracts | 1 suite | result | passed |
| Clean pinned-upstream IntelliFold PyTorch patch + installed reverse check | 1 each | result | passed |
| IntelliFold PyTorch/Metal v2-flash retained-backend fold | 1 | completed structures | 1/1 |
| Retained-backend fold | 1 | pipeline wall time | 92.4 s |
| Retained-backend fold | 1 | pTM / mean pLDDT | 0.719 / 89.8 |
| Retained-backend device probe | 1 | accelerator | `mps` |
| Retained-backend durable MSA copy | 1 | bytes | 100,798 |
| Existing-install upgrade staging | 1 | obsolete wrappers remaining | 0 |
| Debug build + release app assembly/signature verification | 1 each | result | passed |

## Decision and rationale

1. **AlphaFold 3 is retired, not “experimental.”** The official source revision
   and input preparation were correct, but the available Apple-GPU route failed
   the controlled structure-quality check. Studio is GPU-only, so it has no
   trusted AF3 backend to offer.
2. **IntelliFold JAX/Metal is retired as a separate engine.** It shares the
   affected execution family and failed the same target despite receiving the
   same alignment. A prior speed observation cannot outweigh model-quality
   failure.
3. **IntelliFold PyTorch/Metal remains supported.** It passed the same-input
   check, runs on Apple GPU, and continues to offer both v2-flash and full v2.
4. **Compatibility is read-only, not runnable.** Removing enum cases would make
   old project JSON undecodable and hide old scientific outputs. Retaining the
   identifiers without exposing or launching them preserves provenance without
   presenting an unsafe option.
5. **Do not silently fall back.** A saved retired selection, old CLI flag or
   stale config must stop or require a deliberate new choice. Quietly replacing
   it with Boltz, OpenFold or IntelliFold would make the recorded run
   irreproducible.

This supersedes entry 0028's temporary decision to keep the JAX/Metal routes
opt-in and experimental. It does not alter the historical measurements in
entries 0002, 0008, 0013, 0015 or 0024.

## Reproduce

Run long or GPU-bearing checks under `caffeinate`:

```bash
cd /Users/thomasfryer/iProteinStudio

caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu env PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-final-pyc \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py
caffeinate -dimsu env PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-final-pyc \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_ligand_conditioning.py

# Compile the three Swift contract executables from production files.
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /private/tmp/iproteinstudio-iterative-contract
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/RFD3Request.swift \
  Sources/iProteinStudio/Models/PredictionRequest.swift \
  Tests/WorkflowRequestContractHarness.swift \
  -o /private/tmp/iproteinstudio-workflow-contract
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/RunResult.swift \
  Tests/PredictionResultsContractHarness.swift \
  -o /private/tmp/iproteinstudio-results-contract
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract
caffeinate -dimsu /private/tmp/iproteinstudio-workflow-contract
caffeinate -dimsu /private/tmp/iproteinstudio-results-contract

# Prove the reduced patch applies to a pristine copy of the pinned revision and
# corresponds to the installed PyTorch patch.
IF_PATCH_TEST="$(mktemp -d /private/tmp/iproteinstudio-if-patch.XXXXXX)"
git -C /Users/thomasfryer/.iproteinstudio/src/IntelliFold archive --format=tar \
  --output="${IF_PATCH_TEST}/base.tar" \
  4e420db7482b4f50dbb86800ff710ee4ec7c7b7b
mkdir "${IF_PATCH_TEST}/source"
tar -xf "${IF_PATCH_TEST}/base.tar" -C "${IF_PATCH_TEST}/source"
git -C "${IF_PATCH_TEST}/source" apply --check \
  /Users/thomasfryer/iProteinStudio/Sources/iProteinStudio/Resources/pipeline/patches/intellifold_pytorch_mps.patch
git -C /Users/thomasfryer/.iproteinstudio/src/IntelliFold apply --reverse --check \
  /Users/thomasfryer/iProteinStudio/Sources/iProteinStudio/Resources/pipeline/patches/intellifold_pytorch_mps.patch

# One real production-route fold, with MSA server access disabled. The config is
# retained with its output.
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Sources/iProteinStudio/Resources/rfd3/predict_batch.py \
  --config /private/tmp/iproteinstudio-retained-if-config.json
sed -n '1,200p' \
  /private/tmp/iproteinstudio-retained-if-20260820/run_summary.json

/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_intellifold/bin/python -c \
  'from accelerate import Accelerator; import torch; a=Accelerator(); print(a.device); print(torch.backends.mps.is_available())'

caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
open build/iProteinStudio.app
NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash /Users/thomasfryer/.iproteinstudio/setup_pipeline.sh --detect
```

The upgrade launch replaced the staged overlay, removed
`rfd3/scripts/af3_predict_one.py`,
`rfd3/scripts/intellifold_jax_predict_one.py`,
`scripts/alphafold3_adapter.py` and
`scripts/repair_intellifold_jax_cifs.py`, and left all seven supported component
checks at `NHSTATE|…|ok`.

## Limits and what was not tested

- No AlphaFold 3 or IntelliFold JAX inference was rerun: the purpose of this
  change is to make those backends unreachable, and entry 0028 contains their
  controlled evidence.
- Existing managed AF3/JAX environments, parameters and outputs were not
  uninstalled or deleted. Only obsolete executable adapter scripts owned by
  Studio were removed during normal upgrade staging.
- Historical result browsing is covered by a fixture, not by opening every old
  project through the GUI.
- No Intel Mac, non-Metal GPU or CPU product route exists or was tested.

## Next

Do not restore either backend on the strength of a successful launch or speed
measurement. Reconsider only after a pinned Apple-GPU implementation passes a
representative, same-input structural parity suite without silent weight,
operator or precision fallbacks.
