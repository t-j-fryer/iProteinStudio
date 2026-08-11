# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-08-10_

| | |
|---|---|
| **Stage** | Alpha. Builds and runs; not signed or notarised for distribution. |
| **Platform** | macOS 14+, Apple Silicon only. Developed on M4 Max / 64 GB / macOS 26.x. |
| **Repo** | Private — `github.com/t-j-fryer/NanoHunterStudio` |

**Working:** setup wizard, project management, nanobody/mini-binder/peptide design form,
live metrics dashboard, hits gallery, offline 3D structure viewer, target prep,
predictions library.

**Also working:** choice of design predictor (Boltz-2 ± potentials, IntelliFold,
AlphaFold 3, OpenFold-3) with orthogonal checking; measured-optimum scheduling
delegated to NanoHunter's runner; reuse of an existing local NanoHunter/RFD3
install instead of a second multi-GB download; an RFdiffusion3 tab that drives the
validated production pipeline and survives quitting the app.

**Known gaps, in priority order:**

1. **Studio has no measurements of its own.** Every performance number in this repo
   was measured in a sibling repo. No campaign has yet been run end to end
   *through the app*.
2. The RFdiffusion3 **protein path is entirely untested**, and stops after sequence
   design because re-folding a complex needs a target MSA it cannot build —
   see [0004](lab_book/0004-rfdiffusion3-tab.md).
3. RFdiffusion3 campaign **results have no UI**: rankings, apo–holo preorganisation
   and self-consistency are written to disk but must be opened by hand.
4. The IntelliFold JAX backend (1.24x) is installable but **not selectable** —
   `nanohunter_run.sh` hard-assigns its venv and runner, so there is no supported
   route to it. Upstream fix needed — see [0003](lab_book/0003-predictor-choice-and-scheduling.md).
5. OpenFold-3 complex pLDDT has an unresolved scale problem and must not be surfaced in
   the UI — see [0002](lab_book/0002-inherited-speed-lessons.md) §7.
6. No app icon, no Developer ID signing/notarisation.

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
