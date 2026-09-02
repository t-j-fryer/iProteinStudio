---
name: iprotein-run
description: Run iProteinStudio's pipelines from the command line — fold a batch of sequences, run an iterative binder-design campaign, or drive an RFdiffusion3 campaign. Use when asked to predict structures, design binders, generate backbones, install or check engines, or reproduce something the app did. Covers Boltz-2, IntelliFold (PyTorch and JAX/MPS), AlphaFold 3, OpenFold-3, RFdiffusion3, and the MPNN/AntiFold/LASErMPNN designers on Apple Silicon.
---

# Running iProteinStudio from the command line

The app is a front end. Every action is a script, and the app writes its settings
to disk before running them, so any run can be reproduced or scripted.

Read `docs/CLI.md` in this repo for the full command reference. This skill covers
what to do, what to check, and the traps that produce *plausible but wrong*
results rather than errors.

## Orientation

```bash
export ROOT="$HOME/.iproteinstudio"
export NANOHUNTER_ROOT="$ROOT"
bash "$ROOT/setup_pipeline.sh" --detect      # what is installed
```

Never assume an engine is present. `--detect` prints one `NHSTATE|<component>|ok|…`
line per engine; check before offering one to the user.

When `$ROOT/mcp/server.py` is staged and the client is configured, prefer its
typed tools over assembling commands by hand. Create a workflow-specific plan,
show the normalized settings and digest to the user, then call `job_start`.
`job_status`, `job_wait`, `job_cancel`, and `job_resume` operate on durable jobs
that survive the Claude session. The MCP bridge deliberately routes back to the
same commands described below; it does not replace their scientific behaviour.

## The traps

These have all caused real, silent failures in this project. They do not raise —
they produce confident output that is wrong.

**Alignments.** `--require-target-msa` on design runs. Without it an unreachable
MSA server degrades the run to single-sequence mode, which changes the science
without changing the command. For prediction, `"allow_server": false` fails
rather than folding without one.

**A de-novo binder should have no alignment.** `msa: empty`. It has no
homologues; aligning it costs a round trip and adds nothing.

**Boltz ligand atom names move.** They are `element + canonical rank`, and
enabling the affinity head standardises the SMILES *first*, renumbering
everything — the same atoms are `O17,C24,N44` with it off and `O19,C26,N46` with
it on. Regenerate with `boltz_ligand_atoms.py <smiles> <0|1>` whenever the SMILES
or the affinity setting changes. Never reuse names across that change.

**A forced pocket constraint needs potentials.** `force: true` alone exposes a
restraint; only `--boltz-use-potentials` steers towards it.

**RFdiffusion3 length is not binder length.** Foundry's `length` is the total
component count, so a fixed motif in the contig is added on. Pass `--lengths`
(binder residues) to `design_from_yaml.py` and let it do the arithmetic. Writing
`length` into the spec yourself reintroduces
`ComponentValidationError: No valid selections possible`.

**Do not name the ligand twice.** With `input:` + `ligand:`, adding it to the
contig as well duplicates every ligand atom.

**Leave the token buckets alone.** `--intellifold-buckets` and
`--alphafold3-buckets` default to `auto`, which resolves to the exact campaign
token count — the largest measured speed-up available. Setting them undoes it.

## Choosing an engine

| | |
|---|---|
| Boltz-2 | default; fastest; the only affinity head; also generates alignments |
| IntelliFold (PyTorch) | independent second opinion; fast batched, slow unbatched |
| IntelliFold (JAX/MPS) | same weights, ~1.24× faster, ~2× memory, slightly different numbers |
| AlphaFold 3 | strong orthogonal check; no affinity head; weights are the user's to obtain |
| OpenFold-3 | independent check with Apple GPU kernels |

Design loops optimise against whichever engine drives them, so that engine's own
confidence is self-scored. Always check hits with a *different* one.

## Long runs

Anything multi-hour goes under `caffeinate -dimsu`, and RFdiffusion3 campaigns
launch detached with `launch_rfd3_nise_campaign.py` so they survive the shell.
Poll with `status_rfd3_nise_campaign.py`. Do not start a second GPU job while one
is running, and do not benchmark against a live campaign.

## Recording work

This repo keeps a Lab Book (`LAB_BOOK.md`, `lab_book/`). If you change anything —
run an experiment, fix a bug, make a decision with a real alternative — add an
entry from `lab_book/TEMPLATE.md` and link it from the index. Record what you did
*not* test as carefully as what you did. Negative results are worth as much as
positive ones.
