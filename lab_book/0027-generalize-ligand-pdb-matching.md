---
entry: 0027
title: Generalize exact-ligand PDB matching beyond one regression molecule
date: 2026-08-18
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, ligand, pdb, reproducibility, testing]
---

## Context

The stereochemistry fix in [[0026-fix-ligand-conditioning-and-biotin]] was found
through biotin, but its live acceptance also used only biotin. That did not prove
the feature was general. Inspection found no compound-specific production branch,
but did find two generic failure modes: chemical-component search read only the
first 25 results, and unreadable candidate records could be reported as “no exact
match.” A molecule with many stereochemical CCD variants could therefore be missed.

## What was done

`ligand_intelligence.py` now paginates RCSB graph-strict chemical searches until all
candidate CCD identifiers have been collected, de-duplicates identifiers across
pages, and checks the complete InChIKey for every candidate. The code no longer
accepts a first candidate when RDKit cannot calculate exact identity. Missing or
unreadable component records make the external search visibly incomplete instead
of becoming a false negative.

Entry lookups now record partial RCSB failures, and coordinate retrieval reports
when only some sampled entries were usable. Exact CCD codes are still searched
together and entry identifiers are de-duplicated before the user-configured sample
limit is applied.

`Tests/test_ligand_conditioning.py` now treats biotin as only the original atom-map
regression fixture. Generic identity contracts independently exercise enantiomers,
protonation, caffeine, pagination beyond 100 results, incomplete RCSB records, and
multi-CCD entry de-duplication. `Tests/test_live_ligand_pdb.py` retains the diverse
live-service matrix as a reproducible optional acceptance test.

## Results

No performance benchmark was made; these are correctness checks against the live
RCSB service on the machine in the header.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Ligand Python contracts | 7 test functions | result | pass |
| Caffeine | 13 graph candidates | exact CCD / sampled entries | `CFF` / 10 |
| Aspirin | 2 graph candidates | exact CCD / sampled entries | `AIN` / 8 |
| (S)-ibuprofen | 2 graph candidates | exact CCD / sampled entries | `IZP` / 6 |
| beta-D-glucose | 25 graph candidates | exact CCD / sampled entries | `GLC` / 10 |
| Acetate | 2 graph candidates | exact CCD / sampled entries | `ACT` / 10 |
| Caffeine conformer match | 10 coordinates | matched / unmatched | 10 / 0 |
| Aspirin conformer match | 8 coordinates | matched / unmatched | 8 / 0 |
| beta-D-glucose conformer match | 10 coordinates | matched / unmatched | 5 / 5 |

The glucose result is not treated as a failure or rounded up: half of the sampled
experimental coordinates lay outside the generated-state cutoff and remain visibly
unmatched. That is the intended conservative behavior.

## Decision and rationale

**Search by arbitrary molecular graph, then require complete identity.** No CCD code,
common name or molecule-specific SMILES belongs in the production path. Graph search
finds candidates; full InChIKey equality decides identity.

**Prefer an explicit incomplete result to a false “not in the PDB.”** Falling back to
the first candidate or ignoring a failed page is faster, but it can attach evidence
from the wrong stereoisomer or deny evidence that exists. External-service failures
therefore remain distinguishable from a completed search with zero exact matches.

**Do not force every experimental geometry into a computed state.** A PDB occurrence
supports a recommended state only within the RMSD cutoff. Unmatched coordinates are
counted because they may indicate missing conformational sampling or unusual bound
geometry.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_ligand_conditioning.py

caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_live_ligand_pdb.py
```

## Limits and what was not tested

- RCSB is a live external service. Counts can change as structures and chemical
  components are revised.
- The matrix covers neutral, anionic, chiral, aromatic heterocyclic and carbohydrate
  ligands. It does not cover isotopically labelled ligands, organometallics, polymers,
  multi-component salts, covalent adducts or mixtures expressed as dot-disconnected
  SMILES.
- An exact submitted protonation and stereochemical state may correctly have no exact
  CCD even when a differently protonated or stereochemical relative is present. Studio
  does not silently substitute that relative.
- The PDB search and conformer comparison are CPU/network preparation. No GPU model
  was rerun for this change.

## Next

Expose candidate/identity diagnostics in a user-expandable detail view if bench users
need to understand why a related but non-identical deposited component was excluded.
