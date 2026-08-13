---
entry: 0009
title: A prediction-only tab, and an alignment cache shared with the design side
date: 2026-08-13
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [prediction, msa, scheduling, ui]
---

## Context

Both existing tabs design something. Plenty of the work around a design project
is not design at all: fold this set of sequences, fold them against that target,
check what a batch of candidates looks like. Doing that by hand meant writing
YAML, waiting on the alignment server again for a target that had already been
aligned a dozen times, and running every engine at whatever concurrency happened
to be the default.

## Results

### The alignment cache is the point

Folding a 42+74-residue complex takes a couple of minutes. Generating the
alignment for the target can take longer, and it is *the same target* every time
someone folds against it. So the cache is the feature; the folding is the easy part.

Alignments are indexed by **the sequence they describe**, not by filename — the
first record of the A3M, with insertions and gaps stripped. That is deliberate:
every consumer downstream checks that the first record matches the chain it is
attached to, and a mismatch there is the classic way a reused alignment silently
corrupts a run. Keying on the sequence makes reuse safe by construction.

The index is built by scanning everywhere an alignment might already live — the
app's own cache, its projects, and any NanoHunter checkout on the machine.

| | |
|---|---|
| Distinct sequences already aligned on this Mac | **8,024** |
| Cost of building the index | one record read per file |
| Alignments needed by the test batch | 1 |
| Alignments taken from the cache | 1 (server switched off) |

That 8,024 comes from design campaigns going back months. None of it had ever
been reachable outside the run that produced it.

New alignments are generated once, into the shared cache, so the design side
benefits from anything this tab produces and vice versa.

### Per-chain alignment policy

A de-novo binder has no homologues. Aligning it costs a server round trip and
returns essentially itself. Its target usually wants the deepest alignment
available. That is not a per-job decision, and the tab does not present it as one:
each chain is set independently, defaulting to an alignment for partners and
single-sequence for the sequences being screened.

### Batch shapes

Sequences arrive pasted, as FASTA, or as CSV, and fold as monomers, all against
one partner, or each with its own partner from a column. Partners can be small
molecules, so a screen against a ligand is the same operation as against a protein.

CSV column names are matched loosely (`binder`/`sequence`/`seq`,
`target`/`partner`/`chain_b`, `smiles`) rather than forcing one spelling. A FASTA
asked to pair each sequence with its own partner is **refused with the reason** —
a FASTA record has nowhere to record a partner, and guessing would be worse than
stopping.

All three modes were exercised; the refusal was too.

### Scheduling

Jobs are grouped by token bucket so a compiled shape is reused, and each engine
runs at the schedule measured fastest for it rather than a shared default:

| Engine | Processes | Folds per model load |
|---|---:|---:|
| Boltz-2 | 1 | 8 |
| Boltz-2 + potentials | 2 | 4 |
| IntelliFold | 4 | 16 |
| IntelliFold (JAX) | 1 | 4 |
| AlphaFold 3 | 2 | 4 |
| OpenFold-3 | 2 | 1 |

IntelliFold JAX is set to one process deliberately: four processes was fastest
(9.15 s) but needed ~27 GiB, where one process with four inputs was 9.34 s at
6.7 GiB — within 2% for a quarter of the memory. On a machine smaller than this
one the four-process setting would not fit at all.

Overriding either number is possible and warns, because doing so discards the
measurements.

### A bug that would have made the measurements meaningless

The first scheduling loop launched each chunk with `subprocess.run` and then
reset its `running` list. It reported concurrency and executed **serially** — so
IntelliFold's optimum of four processes, which is most of why it is affordable,
would have been a number in a table with no effect on anything. Now `Popen` with
real reaping.

### End to end

Two de-novo binders screened against one shared target — the commonest real
batch — with the MSA server **switched off**:

```
8024 distinct sequences already aligned on this machine
1 of 1 needed alignments came from the cache
boltz: 2 fold(s) in 1 shape group(s), 1 process(es) x 8 input(s) each
2 of 2 folds succeeded          219 s
```

The target's alignment was deduplicated across both jobs, both folded in one
model load, and both structures were written.

## Decision and rationale

**The tab lives inside a project rather than being global.** Predictions get an
output directory, sit next to the design work they relate to, and are saved with
the project. A global tool would need its own storage concept for no gain.

**Boltz generates the alignments**, even when the fold will be done by another
engine. It is the only backend with a first-class MSA-server path, and an A3M is
an A3M. Making each engine fetch its own would multiply server load for identical
results.

**Refusing beats guessing.** Offline mode stops rather than folding without an
alignment; a FASTA asked to pair stops rather than inventing partners. A fold
without a real alignment looks exactly like one with, which is precisely why it
must not happen silently.

Rejected: reusing `RFD3/scripts/run_predictors.py`. It runs one job per process
with no directory batching and no MSA handling, so it would have thrown away the
model-reuse win and the cache — the two things that make this worth having.

## Reproduce

```bash
NEW="$HOME/.nanohunterstudio"
python3 "$NEW/rfd3_scripts/parse_sequences.py" screen.fasta \
  --mode shared --partner "$TARGET_SEQ" --binder-msa empty --partner-msa auto > jobs.json
# fold them, refusing to contact the alignment server
"$NEW/venvs/NanoHunter_boltz/bin/python" "$NEW/rfd3_scripts/predict_batch.py" --config config.json
```

## Limits and what was not tested

- **Only Boltz has actually folded through this path.** IntelliFold, AlphaFold 3,
  OpenFold-3 and IntelliFold-JAX are wired and their schedules are set, but no
  batch has been run through them here. OpenFold-3 in particular has still never
  produced a structure anywhere (see [[0008-self-contained-install-and-remaining-backends]]).
- **Concurrency above one process is untested.** The test batch was Boltz, whose
  optimum is one. The Popen reaping loop has never had two processes in flight.
- **No large batch has been run.** Two jobs, one shape group. Bucket grouping
  across several shapes, and the queue draining behaviour, are unexercised.
- The index was built once over ~10,700 A3M files and took a few seconds; it is
  incremental by mtime and size afterwards, but that incremental path has not
  been timed on a cold cache of that size.
- Ligand partners are supported in the parser and the YAML writer but no fold
  with a ligand has been run through this tab.
- The time estimate uses the same measured seconds as the design tabs, which come
  from a 96-aa monomer. A 500-residue complex will be far slower than it claims.

## Next

1. Run a batch through each engine, and one with two processes in flight.
2. Surface results in the app — structures, confidences, a sortable table.
   Currently the tab writes `predictions.csv` and a folder, and the user opens it.
3. Feed the alignment cache back into the design tabs explicitly, so a campaign
   starts from it rather than only contributing to it.
