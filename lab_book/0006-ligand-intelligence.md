---
entry: 0006
title: Ligand Intelligence — conformer analysis and evidence-based design allocation
date: 2026-08-11
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, ligand, chemistry, ui, pdb]
---

## Context

Until now, a small-molecule campaign took the SMILES, generated **one** RDKit
conformer, and designed a pocket around it. For a rigid ligand that is fine. For
a flexible one it is a silent failure: the campaign completes, the iPTMs and
P(bind) look normal, and the binder was built for a geometry the molecule may
rarely adopt. Nothing downstream can catch that, because nothing downstream knows
what the alternatives were.

The owner proposed a "Ligand Intelligence" layer to sit above the existing
machinery — RDKit for conformers, AtomWorks for structure handling, RCSB for
experimental evidence — and supply the decision logic those tools do not have.
This entry implements it.

## What was done

`Resources/rfd3/ligand_intelligence.py`, in pipeline order:

1. **Chemistry QA** — unspecified stereocentres, formal charge, tautomer count,
   elements MMFF has no parameters for, molecules too small or too large to
   design against. All reported; none silently fixed.
2. **Recognition core vs presentation region** — the user names the atom where a
   linker leaves. The presentation region is the largest acyclic branch at that
   atom; everything else is core. Deterministic and visible in the UI, so a wrong
   guess is correctable rather than invisible.
3. **Ensemble** — ETKDGv3, count scaled to *core* rotatable bonds (20 → 200),
   MMFF94s with a UFF fallback, strain filtering.
4. **Clustering** on core heavy atoms with a symmetry-aware RMSD.
5. **Experimental evidence** — RCSB chemical search for the exact graph, identity
   confirmed by InChIKey, then each instance's observed geometry pulled from the
   ModelServer and matched back onto a computed cluster.
6. **Recommendation and allocation** — which shapes to design against and what
   share of the budget each gets.

`RFD3/scripts/design_from_yaml.py` gained `--conformers path:weight:label`,
building one set of fixtures per conformer per length and splitting the quota by
weight. Additive; absent, behaviour is identical to before.

## Results

### Three silent failures found while testing

Each of these produced plausible output rather than an error, which is exactly
why they are worth recording.

| Bug | Symptom | Cause | Fix |
|---|---|---|---|
| Fixed strain window | ATP: 13 of 200 conformers survived | 10 kcal/mol is nothing for a charged, floppy molecule — MMFF intramolecular electrostatics span tens of kcal/mol | Window scales with flexibility: `min(30, 10 + 2 × core_rotatable)` |
| Fixed cluster threshold | ATP: 13 clusters from 13 conformers | 1.0 Å over 31 atoms separates everything; "13 distinct states" is the same as no clustering | Threshold widens along a ladder until the state count is usable; **the value used is reported**, because it changes what "distinct" means |
| Score 1.0 ≠ same molecule | ATP: 12 instances fetched, **0** matched | The RCSB search returns 1.0 for every component whose graph match succeeded. A query for ATP returns `5FA`, `AQP`, `HEJ`, `ZF9`, `ZSF` at 1.0. Taking the first picked a different compound; its coordinates matched nothing and the experimental evidence quietly vanished | Identity confirmed against the InChIKey connectivity layer before any coordinates are fetched |

The third is the one that matters most. It did not throw, log, or produce an
empty result — it produced a *confident* result with the evidence feature
silently disabled.

### ATP, after the fixes

| | |
|---|---|
| Components confirmed identical | `ATP`, `HEJ` |
| Instances fetched / matched | 12 / 11 |
| Ensemble | 189 of 200 kept, 4 clusters at 2.5 Å |

| Shape | Ensemble | ΔE (kcal/mol) | PDB structures | Budget |
|---|---:|---:|---:|---:|
| A | 88% | +6.1 | 7 | 90% |
| B | 8% | +9.1 | 2 | 6% |
| C | 4% | 0.0 | 2 | 4% |
| D | 1% | +20.5 | 0 | — |

Note that A is not the lowest-energy shape but takes 90% of the budget, because
seven unrelated structures contain it. That is the intended ordering:
experimental observation outranks a force field.

### The linker split does what it is for

A benzylguanine–PEG4 conjugate:

| | Whole molecule | Linker atom named |
|---|---:|---:|
| Atoms treated as core | 36 | 16 |
| Rotatable bonds counted | 19 | 13 |
| Shapes found | 7 | 3 |
| Budget split | 79 / 16 / 5 | 93 / 7 |

Without the split, PEG thrashing reads as conformational diversity and the
budget is spread across shapes that differ only in the tail.

### End to end

Fluorescein hydroxyethylamide → 3 shapes at 50 / 44 / 6 → campaign prepared with
three conformers as 31-atom PDBs carrying the generated component's own atom
names, 0.93–2.15 Å apart, preflight passing. Multi-conformer bin planning
verified separately: 3 conformers × 3 lengths → 9 bins, 500 / 300 / 200 designs
from 50 / 30 / 20 weights, 1,000 total.

Analysis takes ~1 s offline, ~8 s with a PDB search.

## Decision and rationale

**Conformers are written as PDB, not SDF.** Foundry reads PDB/CIF, and — more
importantly — conditioning selections address atoms *by name*. A conformer with
RDKit's default names would silently condition atoms that do not exist in the
generated component. Each chosen geometry is therefore transplanted onto the
reference component's atom order, with the names preserved and checked.

**Force-field energies are never presented as populations.** They rank shapes and
discard strained ones; MMFF cannot support a Boltzmann claim about a charged
molecule in water, and the UI says so.

**Experimental support outranks ensemble fraction, which outranks energy.** The
energies are not accurate enough to order states that are close together, so
population breaks ties before energy does.

**The user can override every state.** The recommendation pre-ticks states, and
unticking one re-normalises the remaining shares rather than shrinking the
campaign. The analysis is advice, not a gate.

Rejected: adding `rcsb-api`/`rcsbsearchapi` as dependencies — plain HTTP against
two documented endpoints avoids pinning two more packages into an environment
that already has version constraints from four model repos. Rejected: clustering
with sklearn — RDKit's Butina is deterministic, already present, and adequate.

## Reproduce

```bash
cat > /tmp/req.json <<'EOF'
{"smiles": "Nc1ncnc2n(cnc12)[C@@H]1O[C@H](COP(O)(=O)OP(O)(=O)OP(O)(O)=O)[C@@H](O)[C@H]1O",
 "search_pdb": true, "max_pdb_entries": 12, "output_dir": "/tmp/atp"}
EOF
/Users/thomasfryer/RFD3/.venv/bin/python \
  ~/Library/Application\ Support/NanoHunterStudio/rfd3_scripts/ligand_intelligence.py /tmp/req.json

# Multi-conformer bin planning
cd /Users/thomasfryer/RFD3
.venv/bin/python -c "
import sys; sys.path.insert(0,'scripts')
from design_from_yaml import parse_conformers
print(parse_conformers('a.sdf:0.5:A,b.sdf:0.3:B,c.sdf:0.2:C'))"
```

## Limits and what was not tested

- **No campaign has been run against a multi-conformer plan.** Bin planning,
  quota splitting and file preparation are verified; nothing has reached the GPU.
  The dTF140 production campaign was folding throughout.
- The attachment atom **was** a typed index; it is now clickable — see the
  addendum below. Still untested with a real pointer: the coordinate mapping is
  measured, but nobody has clicked it.
- **Tier 2 similarity search is not implemented.** Only exact-graph matches are
  used. When there is no exact match the analysis is purely computational, where
  close analogues could have informed torsions.
- Instance fetching is capped (default 30 entries) and stops at the first CCD
  that yields coordinates. A ligand in 3,703 entries is judged on ~12 of them —
  enough to distinguish "one dominant shape" from "promiscuous", not enough to
  quantify frequencies.
- The strain window and cluster ladder are **reasoned, not calibrated.** They were
  chosen so that ATP and fluorescein behave sensibly; two molecules is not a
  validation set.
- The core/presentation rule takes the *largest* acyclic branch. For a molecule
  with two comparable tails it will pick one, and the UI shows which — but it
  could be wrong and the user must look.
- Analysis is only offered for the SMILES route, not for user-supplied structures.

## Next

1. Run one small multi-conformer campaign end to end once the GPU is free.
2. Add the Tier 2 similarity search for molecules with no exact PDB match.
3. Offer the same analysis in the iterative design tab, which has the identical
   problem for ligand targets and none of this machinery.

---

## Addendum, 2026-08-11 — the attachment atom is now clicked, not typed

### Why it needed doing

Picking the wrong atom makes a linker count as recognition core. Its flexibility
then dominates the clustering and the design budget is spread across shapes that
differ only in a floppy tail. With a number box the user gets no feedback at all;
the analysis simply comes back subtly wrong.

### Getting pixel coordinates out of RDKit's SVG

RDKit-JS gives a drawing and a molblock, but no mapping between them. Two
approaches were tried.

**Atom labels — failed.** RDKit draws heteroatom labels as glyph outlines. Their
bounding boxes sit *beside* the atom, not on it. Fitting a similarity transform
against them gave:

| Molecule | mean error | max error |
|---|---:|---:|
| fluorescein-HEA | 27.0 px | 52.6 px |
| ATP | 30.1 px | 62.7 px |

Atoms are 16–28 px apart in these drawings, so the error exceeded the spacing —
this would have selected the wrong atom routinely.

**Bond endpoints — works.** A bond path carries `bond-K atom-I atom-J`, and its
first and last points *are* the two atom centres, except where an end is pulled
back to clear a label. Using only unlabelled ends as anchors:

| Molecule | anchors | mean error | max error | atom spacing |
|---|---:|---:|---:|---:|
| benzene | 6 | 0.03 px | 0.04 px | 127 px |
| fluorescein-HEA | 23 | 2.02 px | 4.69 px | 16.5 px |
| BG-PEG4 | 23 | 1.88 px | 3.14 px | 18.4 px |
| ATP | 10 | 7.42 px | 16.04 px | 27.9 px |

ATP is the worst case — few unlabelled carbons, and double-bond paths contribute
extra sub-paths — but the error is still comfortably under half the atom spacing.

**Picking is nearest-atom, not hit-testing.** A small transparent circle per atom
would have to be larger than the residual error to be reliable, and larger circles
overlap. Taking the nearest atom to the pointer is correct whenever the residual
is under half the spacing, which every case above satisfies with margin.

A bounding-box fit remains as a fallback for molecules with too few anchors.

### Two safeguards

- **The analysis result is shaded back onto the same picture** — green for
  recognition core, amber for the linker. A wrong attachment point stops being an
  invisible numeric error and becomes an obviously wrong picture.
- **The element is cross-checked.** The picker reports the clicked atom's symbol
  alongside its index, and the analysis refuses to run if the symbol at that index
  disagrees. Atom numbering was verified to agree — RDKit preserves SMILES input
  order through the molblock in both the JS and Python paths, checked on four
  molecules — but a silent numbering drift would corrupt every result, so it fails
  loudly instead. Verified: a correct atom is accepted, a mismatched one rejected.

### Limits

- **Nobody has clicked it.** The coordinate mapping is measured against RDKit's
  own SVG from Python, and the atom ordering is verified, but the WKWebView path —
  message handler, hover, click-to-clear — has not been exercised by a pointer.
  That is the remaining risk and it is a UI risk, not a scientific one.
- Anchor accuracy was measured at one canvas size (460×260). The fit is a
  similarity transform so it should scale, but that was not tested.
- The Python-side check of the browser's `getBBox` behaviour is an approximation;
  the label-based approach was rejected on the strength of it, which is safe
  (it was rejected in favour of something more accurate), but the exact browser
  numbers may differ.
