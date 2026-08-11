---
entry: 0004
title: RFdiffusion3 tab, rebuilt on the validated production pipeline
date: 2026-08-10
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, ligand, nise, ui, install]
---

## Context

Follows [[0001-repository-genesis-and-audit]] Finding 3. RFdiffusion3 was not
integrated at all.

This entry records **two** implementations, because the first one was wrong in a
way worth preserving. I initially wrote Studio's own orchestrator, generalising
`RFD3/scripts/run_dtf401_campaign.py`. In parallel, the project owner had a
production pipeline built directly in the RFD3 repo, which is now running a
1,000-backbone campaign (`campaigns/dTF140`). On being shown it, I replaced my
version with it. The rest of this entry is mostly about why.

## Results

### The bug that decided it

My orchestrator wrote the binder length straight into the spec:

```python
spec["length"] = f"{length}-{length}"     # WRONG
```

Foundry's `length` is the **total component count**, not the binder length. With
a contig carrying a fixed motif — `65-150,/0,C1-1` — a 65-residue binder needs a
total of 66. Getting this wrong produces:

```
ComponentValidationError: No valid selections possible with the given constraints.
```

This is exactly how the dTF140 campaign failed on its first launch. It was
confirmed directly there: `65-65` fails, `66-66` resolves to `['65P', '/0', 'C1']`.

My implementation would have failed identically, and my own smoke test did not
catch it — I tested a ligand-only spec with **no contig**, where the motif count
is zero and the buggy arithmetic is accidentally correct. The test passed for the
wrong reason. `design_from_yaml.py:fixed_motif_residue_count` does this properly,
and it generalises: a protein contig `60-60,/0,B1-71` needs a total of 131.

**Studio now never writes `length`.** It writes the contig and lets
`design_from_yaml.py` derive the total per bin.

### Other corrections adopted from the production pipeline

| Thing I had wrong or missing | What the production pipeline does |
|---|---|
| Ligand named in both `input`/`ligand` **and** the contig | Small-molecule specs carry **no contig** — naming it twice duplicates all ligand atoms in the Foundry/MLX output |
| LigandMPNN for small molecules | **LASErMPNN with NISE's exact settings**, imported from `nise_lib` so inverse folding is bit-identical to NISE's own |
| Generic multi-predictor verification | **Boltz-2 with potentials *and* the affinity head**, because the ranking metric needs P(bind) |
| Ranked on iPTM | `nise_lib.rank_score` = `ligand_plddt/100 + pbind`, with `--require-pbind` so a missing affinity value fails loudly instead of silently degrading the ranking |
| Apo check as an afterthought | Top-N re-folded apo, then apo–holo **pocket preorganisation** measured on the holo-defined pocket |
| No validation before GPU time | A **preflight** that resolves every `select_*` key and atom name against the input structure with biotite |
| Full fixture generation | `milestone0_oracle.py --features-only`, which stops after Foundry preprocessing |
| Batch 8 | **Batch 4** in production, for a 33-atom ligand with binders to 150 aa |
| No quota checks | Explicit count checks on backbones, sequences and predictions, so an underfilled bin cannot be marked complete |
| Foreground process | Double-fork + `caffeinate -dims` + PID file, with a separate status script |

Batch size is worth dwelling on. The measured optimum of 8
([[0002-inherited-speed-lessons]] §6) came from 81–131 token fixtures. The
production campaign uses 4 for a larger system. **The optimum falls as the ligand
and binder grow**, which is consistent with the knee being Metal kernel and
temporary-tensor behaviour rather than memory capacity — and it means 8 is not a
universal default. Studio now defaults to 4 and says why.

### What Studio actually does now

```
RFD3View  ─▶ prepare_campaign.py ─▶ <campaign>/config/{design.yaml, campaign.json, ligand.smi}
                                    <campaign>/assets/ligand/{CODE.pdb, ccd/…}
                                    + design_from_yaml.py --stage check   (preflight, GPU-free)
          ─▶ launch_rfd3_nise_campaign.py   (detached, caffeinate, PID file)
          ─▶ status_rfd3_nise_campaign.py   (polled every 15 s)
```

Everything scientific stays in the RFD3 repo. Studio contributes the UI, the
conditioning vocabulary, the spec assembly, and a protein-target path.

### Verification performed

GPU-free only — the dTF140 production campaign was in its backbone stage
throughout, and benchmarking or sampling against a live campaign would corrupt
both.

| Check | Result |
|---|---|
| Atom names from `inspect_target.py` vs `RFD3/assets/fluorescein/atom_selections.json` | **All 31 match exactly** |
| Formal charge for the same molecule | −2, matching |
| Generated `design.yaml` shape | matches dTF140: no contig, no `length`, `select_fixed_atoms: ALL`, selections keyed `L1` |
| Preflight on a valid spec | passes |
| Preflight on a nonexistent atom (`Q999`) | rejected in ~4 s, naming the atom |
| `swift build`, `./build_app.sh` | clean; both helper scripts present in the bundle |

Earlier, before the production pipeline existed and before its campaign started,
my own orchestrator was run through target → fixtures → backbones and produced a
fixture with **31 fixed ligand atoms, 25 buried / 0 partial / 6 exposed RASA,
`is_non_loopy` set on the 80 binder tokens and not on the ligand**, and one real
backbone. Those counts match RFD3's validated fluorescein tensor exactly. That
code is gone, but the numbers confirm the conditioning path itself is sound —
which is why only the length arithmetic needed replacing, not the whole idea.

Test artefacts written into `/Users/thomasfryer/RFD3/oracle/` during that run were
deleted afterwards.

## Decision and rationale

**Drive the RFD3 repo's scripts; do not reimplement them.** The decisive argument
is not effort, it is that the pipeline encodes fixes which are invisible from
outside — the length accounting above being the clearest. A reimplementation
looks correct, passes a plausible test, and fails in production. Rejected
alternative: keep my orchestrator and port the fixes into it, which would have
created a second copy to keep in step with a repo under active development.

**Detach the campaign, and reattach rather than own it.** 4,000 affinity-enabled
Boltz folds is a 45–60 hour job. If it died when the app quit it would be
unusable. Studio launches through the repo's double-forking launcher and treats
the campaign as external state it observes.

**Progress is weighted, not stage-counted.** `predict-holo` is ~55% of the work.
An evenly weighted bar would sit at "nearly finished" for two days.

**The protein path stops after sequence design, and says so.** Re-folding a
designed protein complex needs a NanoHunter template and a cached target MSA,
which cannot be constructed from an RFD3 spec. Backbones and SolubleMPNN
sequences are produced and the UI directs the user to the design tab. Claiming
verification we do not perform would be the worse failure.

**Bury/expose exclusivity is enforced in the UI**, not left to
`patch_foundry_rasa.py`. The patch makes disjoint selections survive; the UI
prevents the contradiction being expressed at all.

**Atom names are never typed.** They are read from the target and offered as
toggles. A typed name that does not exist yields an unconditioned design that
looks like a successful one — the preflight now catches it, but not offering the
mistake is better than catching it.

## Reproduce

```bash
# Prepare a campaign from a Studio request (fast, no GPU)
/Users/thomasfryer/RFD3/.venv/bin/python \
  ~/Library/Application\ Support/NanoHunterStudio/rfd3_scripts/prepare_campaign.py \
  <campaign>/config/studio_request.json
# -> PREPOK|<campaign>/config/campaign.json   (or PREPFAIL|<reason>)

# Everything after that is the RFD3 repo's own, and can be run without Studio:
cd /Users/thomasfryer/RFD3
.venv/bin/python scripts/launch_rfd3_nise_campaign.py --config <campaign>/config/campaign.json
.venv/bin/python scripts/status_rfd3_nise_campaign.py --config <campaign>/config/campaign.json

# Atom-name agreement check
python Sources/NanoHunterStudio/Resources/rfd3/inspect_target.py --kind ligand \
  --smiles 'O=C(NCCO)c1ccc(-c2c3ccc(=O)cc-3oc3cc([O-])ccc23)c(C(=O)[O-])c1'
```

## Limits and what was not tested

- **No campaign has been run end to end through Studio.** Preparation, preflight
  and launch-command construction are verified; the stages after launch are the
  RFD3 repo's, validated there but not through this UI.
- The protein path (`rfd3_protein_campaign.py`) is **entirely untested** — no
  protein target has been through it. Its contig construction
  (`"{min}-{max},/0,{motif}"`) is reasoned from `design_from_yaml.py`, not
  demonstrated. Treat it as unproven.
- The user-supplied-structure ligand route is untested: only the SMILES route was
  exercised. In particular, a ligand whose residue is not a real CCD code will
  need a CCD mirror that Studio does not currently build for that route —
  `prepare_ccd_from_sdf.py` exists in the RFD3 repo and is the obvious way in.
- `inspect_target.py`'s exposure suggestions are heuristic SMARTS, and its protein
  exposure figure is a heavy-atom neighbour count, **not** a SASA calculation. On
  fluorescein it produced a superset of the hand-curated selection: it found all
  six curated linker atoms and additionally proposed the carboxylate.
- Batch-size guidance is now known to be system-dependent (8 for small fixtures,
  4 in production) but the dependence has not been characterised. There is no
  rule here, only two data points.
- CIF ligand extraction is refused rather than implemented.

## Next

- Run one small campaign (say 20 backbones, 2 sequences each) end to end through
  the app once the GPU is free, and record real timings — Studio still has no
  measurements of its own.
- Test the protein path at all.
- Characterise batch size against ligand atom count and binder length; two points
  do not make a rule, and the UI currently presents 4 with more confidence than
  the evidence strictly supports.
- Surface the campaign's results in Studio: `analysis/top100.csv`,
  `analysis/rmsd_metrics.csv` and the apo–holo preorganisation numbers currently
  have no UI at all, so the user must open the folder.
- Consider offering `select_partially_buried`, which RFD3 supports but
  `prepare_ligand_target.py` does not accept — the dTF140 spec uses it directly,
  so the gap is in the spec writer, not the model.
