# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-08-11_

| | |
|---|---|
| **Stage** | Alpha. Builds and runs; not signed or notarised for distribution. |
| **Platform** | macOS 14+, Apple Silicon only. Developed on M4 Max / 64 GB / macOS 26.x. |
| **Repo** | Private — `github.com/t-j-fryer/NanoHunterStudio` |

**Working:** setup wizard, project management, nanobody/mini-binder/peptide design form,
live metrics dashboard, hits gallery, offline 3D structure viewer, target prep,
predictions library.

**Also working:** Ligand Intelligence — chemistry QA, recognition-core vs linker
separation, conformer ensembles weighed against experimental PDB structures, and a
design budget split across the shapes a molecule actually adopts; choice of design predictor (Boltz-2 ± potentials, IntelliFold,
AlphaFold 3, OpenFold-3) with orthogonal checking; measured-optimum scheduling
delegated to NanoHunter's runner; reuse of an existing local NanoHunter/RFD3
install instead of a second multi-GB download; an RFdiffusion3 tab that drives the
validated production pipeline and survives quitting the app.

**Known gaps, in priority order:**

1. **Studio has no measurements of its own.** Every performance number in this repo
   was measured in a sibling repo. No campaign has yet been run end to end
   *through the app*.
2. The RFdiffusion3 **protein path is untested end to end**. It now generates the
   target MSA, re-folds and ranks, but none of those stages has ever run —
   see [0005](lab_book/0005-designer-routing-and-install-detection.md).
3. **AlphaFold 3 and OpenFold-3 cannot check RFdiffusion3 designs** —
   `RFD3/scripts/run_predictors.py` implements Boltz and IntelliFold only. They
   are shown but disabled, with the reason stated in the UI.
5. RFdiffusion3 campaign **results have no UI**: rankings, apo–holo preorganisation
   and self-consistency are written to disk but must be opened by hand.
6. OpenFold-3 complex pLDDT has an unresolved scale problem — see
   [0002](lab_book/0002-inherited-speed-lessons.md) §7. It is a checker only.
7. No app icon, no Developer ID signing/notarisation.

**Deliberately out of scope:** NISE (experimental, stays in NanoHunter); RFdiffusion3
against DNA/RNA (no `rfd3na` checkpoint obtainable on this machine — see
[0001](lab_book/0001-repository-genesis-and-audit.md) Finding 4).

---

## Where the science lives

Studio is a front end. The implementations it drives are in sibling repositories, which
are the source of truth for anything scientific:

- **NanoHunter / iProteinHunter** — `/Users/thomasfryer/NanoHunter` — iterative design
  runner, Boltz-2 / IntelliFold / AlphaFold 3 / OpenFold-3, MPNN + AntiFold designers,
  MSA handling, device throughput calibration.
- **RFD3** — `/Users/thomasfryer/RFD3` — RFdiffusion3 backbone generation on MLX, ligand
  conditioning, length-binned batching, and the production
  RFD3 → LASErMPNN → Boltz-2 affinity/apo campaign that the RFdiffusion3 tab drives.
  `scripts/design_from_yaml.py` is the entry point; it owns the binder-length
  arithmetic and the atom preflight, and Studio must not duplicate either.

---

## Entries

Newest first.

| # | Date | Entry | What it settles |
|---:|---|---|---|
| 0007 | 2026-08-11 | [Predictor settings audit, corrected speed claims, and ligand-atom targeting](lab_book/0007-predictor-settings-audit-and-ligand-targeting.md) | What each engine actually runs with and whether it is optimal, why the old speed multipliers were inverted, and how Boltz ligand atom names shift under the affinity head |
| 0006 | 2026-08-11 | [Ligand Intelligence — conformer analysis and evidence-based design allocation](lab_book/0006-ligand-intelligence.md) | How a flexible ligand's shapes are found, weighed against the PDB, and turned into a design budget — and three silent failures found doing it |
| 0005 | 2026-08-11 | [Designer routing, predictor roles, install detection, and RFD3 options](lab_book/0005-designer-routing-and-install-detection.md) | Why per-component linking beats all-or-nothing, the missing `--workflow` flag, and which predictors belong in which role |
| 0004 | 2026-08-10 | [RFdiffusion3 tab, rebuilt on the validated production pipeline](lab_book/0004-rfdiffusion3-tab.md) | Why Studio drives the RFD3 repo's scripts instead of its own, and the binder-length-versus-total-length bug that decided it |
| 0003 | 2026-08-10 | [Refresh the vendored pipeline, add AlphaFold 3 and OpenFold-3, expose scheduling](lab_book/0003-predictor-choice-and-scheduling.md) | Predictor choice, what scheduling is delegated rather than reimplemented, and which flags must never be overridden |
| 0002 | 2026-08-10 | [Inherited Apple-Silicon speed lessons](lab_book/0002-inherited-speed-lessons.md) | Every measured performance number Studio's scheduling is based on, and the optimisations that were tried and rejected |
| 0001 | 2026-08-10 | [Repository genesis, code audit, and the Lab Book system](lab_book/0001-repository-genesis-and-audit.md) | Starting state, the stale-pipeline finding, private-repo and SMILES/DNA-scope decisions |

---

## Adding an entry

```bash
cp lab_book/TEMPLATE.md lab_book/00NN-short-slug.md
```

Fill in every section, add a row to the table above (newest first), and update
**Current status** if the work changed it. Sections that do not apply get `n/a` and a
reason rather than being deleted — a missing section is indistinguishable from a
forgotten one.
