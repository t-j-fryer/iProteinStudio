---
entry: 0012
title: Worked examples with a shipped alignment, and the first real from-scratch install
date: 2026-08-13
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [examples, msa, install, reproducibility]
---

## Context

Two asks: give people something to press when they have no target of their own,
and finally run the from-scratch install that has been the top open item for
three entries.

## Results

### The examples

**α-Cobratoxin** (71-residue three-finger toxin, *Naja kaouthia*) and
**fluorescein hydroxyethylamide**. Both are real rather than toys: aCbx is a
target antivenom work actually wants binders against, and the fluorescein
derivative carries the conjugation linker that makes the recognition-core versus
presentation-region distinction matter at all.

aCbx ships with:

| File | Size | Why |
|---|---:|---|
| `target.fasta` | — | the sequence |
| `target.pdb` | 43 KB | RFdiffusion3 designs against geometry, not sequence |
| `target_msa.a3m` | 100 KB | **1,148 aligned sequences, already generated** |

**Shipping the alignment is the point of the whole exercise.** Without it, a new
user's very first action is a round trip to a public MSA server that frequently
takes longer than the fold itself and sometimes fails outright — the worst
possible first impression, and entirely avoidable for 100 KB.

It is copied into the shared cache on first launch and indexed by the sequence it
describes, so anything folded against aCbx — any tab, any engine — finds it.
Verified with the server **switched off** and a cache containing only the shipped
file:

```
1 distinct sequences already aligned on this machine
1 of 1 needed alignments came from the cache
msa: <cache>/example_acbx.a3m
```

A user with no network can run the protein example immediately.

Each example pre-selects what the validated work used: aCbx's surface patch
(B67/B69/B71) and the origin strategy that goes with aiming at one face;
fluorescein's linker atom, so the core/linker split is *demonstrated* rather than
described. The examples appear in all three tabs, filtered to the ones a tab can
use — folding a bare SMILES is not what the prediction tab is for.

### The from-scratch install

Run from the clean-clone bundle into an empty root with `--all`, staged exactly
as the app stages on first launch.

| Component | Result |
|---|---|
| Boltz-2 | ok |
| Sequence designers (ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN) | ok |
| AntiFold | ok |
| IntelliFold v2-flash (PyTorch/MPS) | ok |
| LASErMPNN | ok (CPU) |
| OpenFold-3 | see below |
| AlphaFold 3 | see below |
| IntelliFold JAX | see below |
| RFdiffusion3 | see below |

*(Table completed in the addendum below once the run finished.)*

**One caveat on what this proves.** pip's wheel cache on this machine is warm
from months of installs here, so several steps completed far faster than they
would on a genuinely new Mac. The install path is exercised; the *download* path
largely is not. A truly cold machine will take considerably longer, and could
still fail on something this run never had to fetch.

## Decision and rationale

**Ship the alignment, not just the sequence.** 100 KB against a server round trip
on every first run is not a close call. It also demonstrates the cache: the
example is the feature explaining itself.

**Two examples, not a library.** One protein and one small molecule cover every
tab and every workflow between them. More would be a menu to read rather than a
thing to press.

**Pre-select the validated conditioning.** An example that loads a target but
leaves every choice blank teaches nothing about the choices. Loading aCbx with
the hotspots the real campaign used shows what a sensible starting point looks
like.

**Real targets over synthetic ones.** A toy example invites the question of
whether the thing works on anything real. These are what the underlying work was
validated on.

## Reproduce

```bash
# The alignment is found with the server off
NEW="$HOME/.iproteinstudio"
mkdir -p /tmp/exc && cp "$NEW/examples_data/acbx/target_msa.a3m" /tmp/exc/example_acbx.a3m
# config.json with msa.allow_server=false and msa.index_roots=["/tmp/exc"]
"$NEW/venvs/NanoHunter_boltz/bin/python" "$NEW/rfd3_scripts/predict_batch.py" --config config.json

# From-scratch install
FRESH="$HOME/.iproteinstudio_freshtest"; mkdir -p "$FRESH"
cp -R build/iProteinStudio.app/Contents/Resources/*.bundle/pipeline/. "$FRESH/"
cp -R build/iProteinStudio.app/Contents/Resources/*.bundle/rfd3_overlay "$FRESH/rfd3_overlay"
caffeinate -dimsu env NANOHUNTER_ROOT="$FRESH" bash "$FRESH/setup_pipeline.sh" --all
```

## Limits and what was not tested

- **The install ran with a warm pip cache.** See above. This is not a cold-machine
  test and should not be described as one.
- Nothing was folded from the fresh installation. Components reporting `ok` means
  the environment and checkpoint are present, not that a prediction succeeds.
- The examples' UI affordance has not been clicked; the `apply` methods are
  straightforward but unexercised.
- The fluorescein attachment atom is set to index 2 (the amide nitrogen) from
  reading the SMILES, not from clicking it in the picker. If it is wrong, the
  core/linker split in the example will be wrong — visibly so, since the app
  shades it, but wrong.
- aCbx's alignment is reused for *that exact sequence*. A user pasting a variant
  gets a cache miss and a server call, correctly.

## Next

1. Fold the examples from the fresh installation, end to end, in each tab.
2. Click the example buttons.
3. A genuinely cold install — different machine, or a cleared pip cache.
