---
entry: 0007
title: Predictor settings audit, corrected speed claims, and ligand-atom targeting
date: 2026-08-11
author: claude-opus-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, performance, ligand, boltz, ui]
---

## Context

The owner questioned the per-predictor time estimates in the UI and asked for
three things: base them on the compute-scaling figure, show relative speed rather
than exact numbers, and confirm that the settings each predictor actually runs
with are the optimised ones. Plus: why are AlphaFold 3 and OpenFold-3 still
greyed out, stop forcing Boltz for RFdiffusion3 protein targets, and bring
ligand-atom targeting into the iterative tab.

## Results

### The speed claims were wrong, in two different ways

**Wrong source.** The UI said IntelliFold was "~3.8× the time of Boltz-2", taken
from `T01`, which is the *unbatched* configuration (41.5 s at p4). The reference
figure (`Figure_1_compute_scaling`) uses IntelliFold's batched v2-flash
configuration instead — its caption says so explicitly. Batched, IntelliFold is
**11.4 s**, i.e. roughly Boltz's equal and the second-fastest engine. Calling it
3.8× slower was not a rounding issue; it inverted the ranking.

Best-schedule seconds per prediction, 96-aa SUMO with a cached MSA:

| Engine | Unbatched | Batched |
|---|---:|---:|
| Boltz-2 | 10.9 (p1) | 10.9 |
| IntelliFold v2-flash | 41.5 (p4) | **11.4** (p4 × dir16) |
| Boltz-2 + potentials | 21.4 (p2) | 21.4 |
| AlphaFold 3 | 27.7 (p2) | 22.1 (p2 × b4) |
| OpenFold-3 | 27.5 (p2) | 27.5 |

**False precision.** Even the right multiplier is misleading on screen: these
move with scheduling mode, token count, recycles, potentials and machine. The UI
now shows a four-step bar and a band ("fastest", "about twice the time", "roughly
2–3×", "much slower unbatched"), and the band is **scheduling-mode aware**, which
is the useful thing to convey: choosing Batched mode is what makes IntelliFold
affordable.

**A third bug, found while fixing those.** The time estimate divided the
best-schedule seconds by the process count — but the process count is already
baked into those seconds. Every estimate was several times too optimistic.

### Settings audit

Verified line by line against `nanohunter_run.sh`, and now shown in the design
form under *What settings will actually be used*.

| Engine | Settings | Verdict |
|---|---|---|
| **Boltz-2** | GPU accelerator, 1 device, 0 workers, 3 recycles, p1. No `PYTORCH_MPS_PREFER_METAL` / `FAST_MATH`. Host thread limits deliberately **not** applied. | **Optimal.** The omissions are the point: the MPS switches were measured useless and the thread limit made Boltz *slower*. |
| **AlphaFold 3** | `jax_backend=mps`, XLA attention, 10 recycles, 1 diffusion sample, buckets `auto`, persistent JAX compile cache, async dispatch off. | **Optimal**, with one gap: native directory batching only happens in Batched scheduling (~1.4×). |
| **OpenFold-3** | MLX attention/triangle/activation kernels, 3 recycles, 1 sample, 1 seed, p2. | **Optimal.** Highest memory footprint of the four, which is what caps its concurrency. |
| **IntelliFold** | v2-flash, fp32 (Accelerate rejects fp16/bf16 here), 10 recycles, `OMP_NUM_THREADS=1` + `VECLIB_MAXIMUM_THREADS=1`, buckets `auto`, CUDA-cleanup patch applied. | **Not optimal.** Runs on the **PyTorch** backend. The JAX backend is ~1.24× faster and is what the reference figure plots, but there is still no route to it through the runner — `INTELLIFOLD_VENV` and `INTELLIFOLD_RUNNER` are hard-assigned, and the JAX path takes AlphaFold 3 JSON rather than NanoHunter YAML, so it needs an adapter that does not exist. |

That last row is the honest answer to "are you using the optimised ones": three
of four yes, IntelliFold no, and the shortfall is ~1.24×.

### AlphaFold 3 as an RFdiffusion3 checker — now wired

`RFD3/scripts/run_predictors.py` implemented Boltz and IntelliFold only, which is
why both AF3 and OpenFold-3 were greyed out. AF3 is now wired through a new
`scripts/af3_predict_one.py` that reuses NanoHunter's **existing**
`alphafold3_adapter.py` for YAML→JSON and for normalising the output back to the
`model_0.cif` + confidence contract. Reusing that adapter rather than writing a
second one keeps one definition of the conversion.

Two bugs in that change were caught only by *running* it, not by
`python -m py_compile`, and both would have surfaced the first time a user
selected AlphaFold 3:

- `SUPPORTED` was referenced in the argument check but never defined — a
  `NameError` on any `--predictors` value.
- The OpenFold branch pointed at `openfold_predict_one.py`, a script I had
  decided not to write. It would have accepted the flag and then failed on a
  missing file.

Both are the same lesson as everything else in this entry: a syntax check is not
a test. `run_predictors.py` now rejects OpenFold-3 by name with the supported
list, and accepts `boltz,alphafold3` without error.

**OpenFold-3 stays gated**, and the reason is now stated in the UI. Its input
needs a query JSON and a runner YAML built by `build_openfold_query_json` and
`write_openfold_runner_yaml` — bash functions with embedded Python heredocs
inside `nanohunter_run.sh`, ~130 lines, not callable standalone. Transcribing
them blind, with no way to test while the GPU is busy, is the same class of move
that produced the length bug in [[0004-rfdiffusion3-tab]] and the RCSB
score-1.0 bug in [[0006-ligand-intelligence]]. The right fix is to extract them
upstream into scripts both callers can use.

### RFdiffusion3 protein targets no longer force Boltz

Boltz was pinned because the ranking metric needs P(bind) and only Boltz has an
affinity head. That head is trained on small molecules, so for a protein target
the justification evaporates — designs are ranked on confidence and any engine
will do. The verification card now differs by target kind.

### Ligand-atom targeting in the iterative tab

Selected atoms become a Boltz `pocket` constraint:

```yaml
constraints:
  - pocket:
      binder: A
      contacts: [[B, C34], [B, C41], [B, O23]]
      max_distance: 6.0
      force: true
properties:
  - affinity:
      binder: B
```

Verified to parse in the Boltz environment with the contacts as `[chain, atom]`
pairs.

**The atom names are the dangerous part.** Boltz names ligand atoms as
`element + canonical RDKit rank + 1`, and enabling the affinity head
*standardises the SMILES first*, which renumbers everything. Measured on
fluorescein hydroxyethylamide:

| | linker atoms |
|---|---|
| affinity head **off** | `O17, C24, N44, C46, C45, O21` |
| affinity head **on** | `O19, C26, N46, C48, C47, O23` |

Same atoms, different names. A name cached across that change constrains the
wrong atoms, and the run still succeeds. So: names are regenerated whenever the
SMILES or the affinity setting changes, the request records what they were
generated for, and a stale set **blocks the run** rather than warning.

Two further behaviours worth recording:

- **`force: true` alone does almost nothing.** It exposes the restraint as a
  distance restraint, but only `--boltz-use-potentials` actively steers towards
  it. Studio now passes the flag automatically whenever forced contacts exist —
  writing one without the other looks like targeting while barely targeting.
- **There is no "keep this atom exposed" field.** Omitting the linker from the
  contact list removes the pull towards it; it does not push it outwards. The UI
  says so, and linker exposure has to be checked in the results.

Atom indices from the 2D depiction are mapped to Boltz names by the helper. When
the affinity head standardises a charged molecule the graphs no longer match atom
for atom, so the mapping falls back to comparing the **charge-stripped skeleton**,
which is the right granularity — protonation changes names but not which atom is
which.

### Conformers in the iterative tab — deliberately absent

The RFdiffusion3 tab designs against chosen ligand geometries because RFD3 takes
a fixed structure. Boltz builds its own conformer from the SMILES, so there is
nothing to choose between and no allocation to make. The iterative tab therefore
gets the chemistry checks and the core/linker split — which is what makes atom
selection sensible — but not the multi-conformer machinery. The UI says why.

## Reproduce

```bash
BOLTZ="$HOME/Library/Application Support/NanoHunterStudio/venvs/NanoHunter_boltz/bin/python"
SCRIPTS="$HOME/Library/Application Support/NanoHunterStudio/rfd3_scripts"
SMI='O=C(NCCO)c1ccc(-c2c3ccc(=O)cc-3oc3cc([O-])ccc23)c(C(=O)[O-])c1'
"$BOLTZ" "$SCRIPTS/boltz_ligand_atoms.py" "$SMI" 0   # names without the affinity head
"$BOLTZ" "$SCRIPTS/boltz_ligand_atoms.py" "$SMI" 1   # names with it — different
```

## Limits and what was not tested

- **No prediction was run.** The dTF140 production campaign was folding
  throughout, so everything here is static verification: flags read from the
  runner, YAML parsed in the Boltz environment, atom names generated and
  compared. Nothing was folded.
- **`af3_predict_one.py` has never executed.** It is a faithful transcription of
  the runner's own AF3 invocation and reuses the same adapter, but it is unproven.
  Its bucket choice allows a flat 40 tokens per ligand, which is a guess.
- The speed bands are from one machine and one workload (96-aa SUMO). They are
  presented as bands partly for that reason.
- Ligand-atom targeting is verified as far as "the YAML parses and the names are
  the ones Boltz would assign". Whether a pocket constraint on those atoms
  actually steers the design where intended is unmeasured.
- The charge-stripped skeleton match is exercised on one molecule.

## Next

1. Extract `build_openfold_query_json` and `write_openfold_runner_yaml` from
   `nanohunter_run.sh` into standalone scripts, then wire OpenFold-3 into the
   RFdiffusion3 checker the same way AF3 now is.
2. Give the IntelliFold JAX backend a route through the runner — it needs an
   adapter from NanoHunter YAML to AF3 JSON, which `alphafold3_adapter.py`
   already contains. That is the ~1.24× currently being left on the table.
3. Run one small campaign with a pocket constraint and check the targeted atoms
   really are the buried ones and the linker really is exposed.
4. Studio still has no measurements of its own. Four entries running.
