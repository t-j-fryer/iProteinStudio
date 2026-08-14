# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-08-14_

| | |
|---|---|
| **Stage** | Alpha. Debug and release builds pass; a standalone managed install has completed acceptance folds; not signed or notarised. |
| **Platform** | macOS 14+, Apple Silicon only. Developed on M4 Max / 64 GB / macOS 26.x. |
| **Repo** | Private — `github.com/t-j-fryer/iProteinStudio` (renamed from NanoHunterStudio) |
| **Runtime** | `~/.iproteinstudio` — **not** Application Support: a space in the path breaks every Python console-script shebang |

**Working:** setup wizard with per-engine choice, worked examples (α-cobratoxin
with its alignment included, and fluorescein), project management, a
prediction-only tab that reuses every alignment on the machine, nanobody/mini-binder/peptide design form,
live metrics dashboard, hits gallery, offline 3D structure viewer, target prep,
predictions library.

**Also working:** Ligand Intelligence — chemistry QA, recognition-core vs linker
separation, conformer ensembles weighed against experimental PDB structures, and a
design budget split across the shapes a molecule actually adopts; choice of design predictor (Boltz-2 ± potentials, IntelliFold v2-flash or full v2,
AlphaFold 3, OpenFold-3) with orthogonal checking; measured-optimum scheduling
delegated to NanoHunter's runner; a pinned standalone installation that does not
need a sibling checkout, with explicit reuse of an existing NanoHunter/RFD3
install as an option; an RFdiffusion3 tab that drives the
validated production pipeline and survives quitting the app.

**Known gaps, in priority order:**

1. Completed Iterative runs remain on disk but do not reappear as project run
   history after the app restarts. Persistent recovery/results UI is the most
   important remaining robustness and usability gap.
2. The RFdiffusion3 protein fixture and MLX backbone path now have a real local
   GPU acceptance run, but SolubleMPNN, target-MSA generation, verification and
   ranking remain untested end to end from a GUI click — see
   [0015](lab_book/0015-gui-gpu-and-usability-audit.md).
3. Accessibility labels now cover examples, primary Start actions, navigation
   and the active-run banner, but the remaining forms have not had a complete
   VoiceOver, keyboard-focus, large-text or contrast pass.
4. AlphaFold 3's environment installs, but its gated `af3.bin` parameter file
   cannot be distributed or downloaded by Studio; the user must supply it.
5. RFdiffusion3 campaign **results have no UI**: rankings, apo–holo preorganisation
   and self-consistency are written to disk but must be opened by hand.
6. OpenFold-3 complex pLDDT has an unresolved scale problem — see
   [0002](lab_book/0002-inherited-speed-lessons.md) §7.
7. No app icon, no Developer ID signing/notarisation, no self-update.

**Deliberately out of scope:** NISE (experimental, stays in NanoHunter); RFdiffusion3
against DNA/RNA (no `rfd3na` checkpoint obtainable on this machine — see
[0001](lab_book/0001-repository-genesis-and-audit.md) Finding 4).

---

## Where the science lives

Studio is a front end. The implementations it drives originate in sibling
repositories, which remain the development references for scientific behaviour.
They are not runtime dependencies of a standalone install:

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
| 0015 | 2026-08-14 | [Exercise real GUI GPU jobs and audit the app as a product](lab_book/0015-gui-gpu-and-usability-audit.md) | Real MPS/MLX launch evidence, active navigation, two acceptance bugs, and the prioritized usability/accessibility roadmap |
| 0014 | 2026-08-13 | [Promote the standalone runtime and keep workflow navigation available](lab_book/0014-runtime-promotion-and-persistent-navigation.md) | Why navigation stays visible during campaigns, how concurrent starts are blocked, and which validated runtime the GUI uses |
| 0013 | 2026-08-13 | [A standalone install with both IntelliFold v2 models and bundled nanobody MSAs](lab_book/0013-standalone-intellifold-and-scaffold-msas.md) | Managed caches, pinned sources/checkpoints, v2-flash versus full-v2 routing, scaffold alignments, and real isolated-root acceptance runs |
| 0012 | 2026-08-13 | [Worked examples with a shipped alignment, and the first real from-scratch install](lab_book/0012-worked-examples-and-fresh-install.md) | Why the aCbx alignment ships with the app, and what a from-scratch install actually proves |
| 0011 | 2026-08-13 | [Rename to iProteinStudio, per-engine installs, and a clean-clone check](lab_book/0011-rename-and-fresh-user-install.md) | The local paths that were being shipped, per-engine installation, and what a new user actually receives |
| 0010 | 2026-08-13 | [A fresh install was missing the entire RFdiffusion3 script layer](lab_book/0010-shipping-the-rfd3-overlay.md) | Why a clean clone could not run anything, how the overlay ships, and exactly what an update does and does not carry |
| 0009 | 2026-08-13 | [A prediction-only tab, and an alignment cache shared with the design side](lab_book/0009-prediction-tab.md) | Why the MSA cache is the feature rather than the folding, how batches are shaped, and the per-engine schedules |
| 0008 | 2026-08-11 | [Self-contained installation, OpenFold-3 and the IntelliFold JAX backend](lab_book/0008-self-contained-install-and-remaining-backends.md) | Why the old install path could never have worked, the three ways a copied venv stays tied to its origin, and the last two backends |
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
