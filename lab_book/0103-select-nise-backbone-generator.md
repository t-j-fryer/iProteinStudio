---
entry: 0103
title: Select the NISE backbone generator
date: 2026-09-06
author: gpt-6
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [nise, rfd3, nesso, esm, resume, ui, packaging]
---

## Context

Following [[0102-separate-nise-stages-and-add-nesso]], the user requested a choice
of RFdiffusion3 or the existing Protein Hunter hallucination for initial NISE
backbones. They corrected their requested default from 12 to **100** and asked
whether NESSO could reuse ESM from another installed tool. Earlier authorization
to update the app and DMG remains in scope.

Read-only audit of `NanoHunter/output/nise_fluorescein/phase0/cycle00` found 100
starting YAMLs (`L000`–`L099`) and 100 corresponding model-0 predictions, plus
their reference PDB copies. The historical campaign's later `config.json` says
12 and `resume: true`; it is not authoritative evidence of the original starting
population. Its summary reports six trajectories. The current Stage-1 refinement
recipe is not claimed to reproduce the old run exactly.

## What was done

Added `backbone_method` (`protein-hunter` by default, or `rfdiffusion3`) and
`rfd3_num_bins` (five) to Swift, the shared Python contract, MCP schema and guide.
New requests default to 100 starts. Existing explicit counts and requests missing
the new generator field retain their previous Protein Hunter behavior. Small
trial retains the generator; Default settings restores Protein Hunter and 100.
The UI exposes RFdiffusion3 length groups only when selected, shows actual lengths
and separate diffusion/Boltz counts, and requires the selected engine install.

The managed adapter calls the existing shipped ligand preparer, Foundry fixture
builder and MLX generator. It explicitly uses 200 steps, two recycles, BF16,
batch eight and two queues per length group, sequential groups. These settings
are inherited from the existing generator, not a new measured NISE optimum.
One fixed ligand conformer is prepared with the saved seed. No linker exposure
or buried-atom selection is inferred. Backbones are audited for binder length,
finite coordinates, chains and exact ligand atom names, then become initial
lineages for the existing NISE refinement/gate/expansion and optimisation code.
No scores are fabricated for diffusion backbones and no method substitution is
allowed on failure.

The opt-in `STUDIO_RFD3_AUDIT_RESUME=1` generator path atomically saves each
completed native batch's accepted PDB/metadata hashes, rejected samples and seed
cursor. Uncommitted outputs are archived before replay. Changed committed inputs
or artifacts fail. Each queue loads its weights once across batches; completed
queue replay skips the weight load. All RFdiffusion3 queues finish before Boltz
or NESSO starts. The broker fingerprints RFdiffusion3 scripts, oracle, checkpoint,
EMA export and engine code alongside the NISE snapshot, under its existing lease.
The RFdiffusion3 overlay stamp is updated so existing installs receive the helper.

NESSO already installs its pinned ESM-2 650M model/tokenizer automatically. The
installed Protenix source uses an ESM-2 3B/ISM path, while AntiFold uses an
inverse-folding architecture; sharing their Python environments or substituting
their checkpoints would be incorrect. Added optional reuse of exact SHA-256
matching assets from configured Hugging Face/Studio caches into NESSO's owned
directory. The installer downloads missing/nonmatching assets normally. No
NESSO or ESM model weights are distributed in the app.

Updated `docs/NISE.md`, README, release notes, model dependency text and tests.

## Results

No scientific performance measurements — implementation and fixture validation.
Swift debug build passes. The first sandboxed build failed writing the standard
Clang cache and emitted secondary SDK mismatch diagnostics; the same build passed
with cache access. All four executable Swift contract harnesses also passed.

| Verification | Result |
|---|---|
| NISE contracts, including generator provenance | 9 passed |
| NESSO contracts, including exact ESM cache reuse | 11 passed |
| RFdiffusion3 atomic batch helper | 2 passed |
| Full NISE search with both model-boundary fixtures | 7 passed |
| RFdiffusion3 adapter and actual generator loop fixtures | 2 passed |
| Existing RFdiffusion3 target export / weight provenance | 1 / 4 passed |
| Existing bundled partial/motif examples, Foundry preflight | Passed |
| MCP bridge / vendor policy | 17 / 1 passed |
| Swift debug and release builds / four Swift harnesses | Passed |
| Unsigned-beta, update and packaged-resource contracts | Passed |
| DMG integrity and archive checksums | Passed |
| Mounted DMG app versus build output | All 387 entries match hashes, modes and symlink targets |
| Isolated GUI | Both selector choices exercised; 100 starts, length groups and 2,400 initial Boltz budget inspected |

The MCP loopback test initially lacked sandbox socket permission; it passed
unchanged with loopback access. The worked-example preflight initially ran in
the Boltz test environment without Biotite; it passed using RFdiffusion3's actual
environment. The initial packaging check still expected MCP v11; the contract
now requires v12 and explicitly checks the two new RFdiffusion3 helper resources.

Packaged version **0.2.0 build 23** at `build/iProteinStudio.app` and
`build/unsigned-beta-0.2.0-23/`. Build 22 had been reserved in the shared working
tree during this pass; this package uses a new build number. MCP is v12, bridge
1.6.0. Release build output is saved as `BUILD_LOG.txt` beside the artifacts.
GUI screenshots are in `gui-check/`. The GUI used a temporary bundle identity,
isolated workspace, disabled update flags and inert core-installation markers;
it did not launch inference or install/download an engine.

Archive checksums:

```text
f34ba131abbd61192a4b98232e4cf9ad2adf04907e8a852de4f875349e3dde01  iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg
d2f985c1ed67bf9985edc0ae9e01508aaa566fd4f04ff13a714ba439f42d4e3f  iProteinStudio-0.2.0-unsigned-beta-apple-silicon.zip
```


## Decision and rationale

Kept Protein Hunter as the default generator and made RFdiffusion3 explicit and
experimental. Reused the existing downstream NISE funnel rather than treating
diffusion output as already Boltz-validated trajectories. Fixed-length groups
amortize fixtures and worker loads; the form makes the deterministic distribution
visible. NESSO remains optional and its own pinned environment avoids dependency
conflicts, while exact cache reuse avoids unnecessary repeated downloads.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
python3 Tests/test_nise_contract.py
python3 Tests/test_nesso_screen.py
python3 Tests/test_rfd3_batch_resume.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_science.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_rfd3.py
python3 Tests/run_swift_contracts.py
swift build
release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No fresh real-model RFdiffusion3-to-NISE campaign, real NESSO inference or fresh
network installation was run. The generator tests substitute model outputs but
execute the real batch loop; the adapter test executes the actual RDKit ligand
preparer and substitutes fixture/diffusion inference. These establish software
routing, lifecycle and checkpoint behavior, not binding accuracy, robustness of
every ligand's chemistry, model memory stability or throughput. A declared small
end-to-end acceptance campaign and screening comparison remain necessary before
making performance or scientific-efficacy claims. Existing lab measurements are
not reused as measurements of this new combined workflow.

No model weights committed or packaged; no public release, Developer ID signing,
notarization or second-Mac installation is part of this pass.
