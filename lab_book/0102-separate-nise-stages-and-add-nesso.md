---
entry: 0102
title: Separate NISE stages and add optional NESSO screening
date: 2026-09-06
author: gpt-6
type: port
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [nise, nesso, ui, screening, residency, reproducibility]
---

## Context

The user requested inclusion of the beta NESSO work, a clearer separation of
initial backbone generation from NISE optimisation, and control over sequences
advanced per cycle per trajectory. They explicitly chose NESSO screening before
Boltz with an adjustable shortlist. This follows [[0095-integrate-ligand-nise]]
and the build-18 package in [[0098-package-nise-app-and-dmg]].

The old tab's 12 starts was a reference default (not a model limit). Its UI cap
was 100 starts and 12 trajectories. Phase-0 budgets were hidden in the adapter,
and `--beam 1` was hard-coded. The label “sequences per trajectory” obscured the
upstream sampler's actual per-parent semantics.

## What was done

- Split the native form into initial backbone generation and optimisation.
  Reused the app's editable numeric controls and added separate calculated
  upper bounds for initial, first-cycle, later-cycle and total optimisation
  predictions. Increased explicit input ranges without changing reference
  defaults or claiming throughput at the new limits.
- Exposed Phase-0 refinement rounds, refinement/gate samples and expansion
  samples. Exposed upstream `beam` as sequences advanced per trajectory, while
  naming `nise_seqs` correctly as samples per parent. Saved advancement and
  per-trajectory stopping state alongside each cycle.
- Added backward-compatible request decoding, shared Python validation and a
  compatible extension of `nise-v1.json`; MCP contract is now v10 / bridge 1.5.0.
- Ported beta's pinned NESSO source/patch, dependency lock and asset identities
  into the deliberately protected NISE vendor directory. Removed machine paths
  from portable assets and added explicit hashes for ESM configuration/tokenizer
  files. Retained Apache-2.0 notices and upstream provenance.
- Added optional managed NESSO installation/detection/removal through Engines.
  It uses an isolated versioned component, Python 3.12.10 and a hash-locked
  environment. The install receipt is published after verification. Existing
  valid versions are not changed in place; incomplete downloads can resume.
- Added sequential NESSO/ESM model workers under the same campaign process group
  and shared broker lease. Dense inference explicitly uses MPS, float32, five
  recycles and two-stage refinement; all assets are resolved offline. Model
  reuse within a screen is implemented. Cross-cycle reuse is experimental and
  retains the separate NESSO and Boltz workers without overlapping their calls.
- Screened optimisation sequences by NESSO binding probability separately within
  each trajectory, with name-based tie-breaking and a saved shortlist. All
  candidates, including rejections, retain scalar outputs and input/artifact
  hashes. Boltz ranking and self-consistency remain the advancement criteria.
- Added a derived `nesso_screening.csv`, an Open Screening Table action, and
  separately named NESSO metrics in native/MCP folded-candidate results.
- Documented stage semantics, budget multiplication, default 12, optional
  installation, scores, resume and experimental limitations in `docs/NISE.md`.

## Results

No new scientific performance measurements. The upstream evidence is beta Lab
Book 0044 and its `nesso_macos` validation report, on their stated M4 Max inputs;
that evidence establishes native-MPS portability, not designed-binder ranking
accuracy or this Studio adapter's real-model performance.

| Check | Result |
|---|---|
| NISE request, broker plan, checkpoint and result contracts | 7/7 pass |
| NESSO screening, real queue client with synthetic worker, detection, provenance and replay | 10/10 pass |
| Full NISE search / preorganisation fixtures, including beam two and NESSO shortlist | 6/6 pass |
| Native shared-job regression suite | 9/9 pass |
| MCP bridge regression suite | 17/17 pass |
| Swift request migration, core, result and iterative executable harnesses | All four pass |
| Installer component, hardening and dependency-lock contracts | Pass (hardening required host process-list access) |
| Vendoring guard | Pass |
| Production Swift build and packaged-resource contract | Pass |
| App deep strict signature; read-only DMG integrity and packaged resources | Pass |
| Built app versus DMG copy | All 385 entries match by file hash, mode and symlink target |
| DMG and ZIP SHA-256 checks | Both pass |
| Isolated native UI layout check | Pass at 900 × 652 window points; both stages and NESSO guidance inspected |

Packaged version **0.2.0 (21)** at `build/iProteinStudio.app` and
`build/unsigned-beta-0.2.0-21/`. Builds 19–20 existed by packaging time and were
retained. This is an ad-hoc-signed, unnotarized `dirty-local-test` beta; no
release or feed was published. Build logs and three UI screenshots are retained
beside the package (`BUILD_LOG.txt`, `gui-check/`).

DMG SHA-256:
`16cd9ee4e8057bc6e16fa652812e24577af77de1a5e190ba1076b59945310605`.
ZIP SHA-256:
`de45e2f7c2be0c72de41ebfab3c05cc57e0b5b3925d335a2f7f0d1fb13e3ddc1`.

The visual check used a temporary app copy with a distinct bundle identifier,
updates disabled, `IPROTEINSTUDIO_TEST_SUPPORT_ROOT`, and synthetic installation
sentinels. No prediction was launched. The shipped binary/resources were
unchanged. Launch Services was needed to keep this temporary GUI alive; direct
child launch was cleaned up by the command runner. Window capture and scrolling
were addressed by the temporary process ID, and the temporary app was closed
when inspection finished.

## Decision and rationale

Keep NESSO off by default and expose it as an experimental prescreen, as the user
requested. It cannot generate atomic backbones. A final-only comparison would
not implement the requested shortlist, and replacing Boltz's probability with
NESSO's would change the objective and conflate model scores.

Keep the original broad-search funnel separate from screening. Exposing its
existing parameters ports established behaviour; adding a new structure engine
or changing its self-consistency thresholds would be a separate scientific
intervention. Keep the original one-parent recipe as the default, while allowing
wider upstream beams explicitly. More parents multiply per-cycle sampling;
the UI reports that multiplication before launch.

The default screen closes its NESSO/ESM worker before Boltz prediction. Keeping
both families across cycles is experimental because this combined lifetime has
not had a real-model memory soak or a paired throughput comparison. The upstream
per-record preprocessing path is preserved; no feature-preparation speed claim
is made.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
python3 Tests/test_nise_contract.py
python3 Tests/test_nesso_screen.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_science.py
python3 Tests/run_swift_contracts.py
bash Tests/test_installer_component_contract.sh
bash Tests/test_installer_hardening_contract.sh
python3 Tests/test_installer_lock_contract.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_mcp_bridge.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-nise-modules \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-nise-modules \
  swift build --disable-sandbox --skip-update
release/release_app.sh --unsigned-beta --allow-dirty
bash Tests/test_packaged_resource_bundle.sh build/iProteinStudio.app
(cd build/unsigned-beta-0.2.0-21 && shasum -a 256 -c SHA256SUMS.txt)
```

The process-list/loopback contracts require normal host permissions: the
sandboxed installer-hardening run failed because its synthetic worker could not
be discovered with `pgrep`; the host-permission rerun passed. No assertion was
weakened. An initial queue fixture accidentally used its own mocked client; the
fixture was corrected to exercise the real client against a synthetic process.

## Limits and what was not tested

- No new NESSO checkpoint inference, full ligand campaign, affinity-accuracy
  benchmark, screening enrichment comparison, memory soak, length sweep or
  cross-hardware speed measurement. Computational scores are not binding hits.
- The managed NESSO download/install route has not been exercised end to end
  against network services. Existing beta source/assets were inspected read-only;
  no existing environment was changed or weight redistributed.
- Wider budget ranges have validation/fixture coverage, not large-campaign
  runtime or memory validation. A shortlist can discard useful candidates.
- Full macOS accessibility and enlarged-text interaction, second-Mac installation,
  notarization and Sparkle update installation are outside this pass. Basic native
  layout inspection was completed; it does not establish those broader checks.

## Next

Use a declared bounded real-model NESSO/Boltz screening acceptance campaign,
then a paired screened/unscreened ranking comparison before changing defaults.
Measure ESM, preprocessing, NESSO, Boltz, model loads and full campaign wall time
separately; include interruption, cancellation, orphan cleanup and a memory soak.
