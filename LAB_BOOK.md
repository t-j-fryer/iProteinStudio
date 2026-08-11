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

**In progress:** vendored-pipeline refresh, AlphaFold 3 + OpenFold-3 predictor support,
measured-speed scheduling, RFdiffusion3 tab.

**Known gaps, in priority order:**

1. The vendored `nanohunter_run.sh` is ~1,250 lines behind upstream, so the app cannot
   yet express any of the optimisation work — see [0001](lab_book/0001-repository-genesis-and-audit.md).
2. The design pipeline is hard-coded to Boltz → IntelliFold; there is no predictor choice
   in the data model.
3. RFdiffusion3 is not integrated at all.
4. OpenFold-3 complex pLDDT has an unresolved scale problem and must not be surfaced in
   the UI — see [0002](lab_book/0002-inherited-speed-lessons.md) §7.
5. No app icon, no Developer ID signing/notarisation.

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
  conditioning, length-binned batching.

---

## Entries

Newest first.

| # | Date | Entry | What it settles |
|---:|---|---|---|
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
