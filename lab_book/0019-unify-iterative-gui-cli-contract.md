---
entry: 0019
title: Unify the iterative GUI and CLI contract
date: 2026-08-17
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, ui, cli, boltz, intellifold, alphafold3, epitope, reproducibility]
---

## Context

An app-launched mini-binder run failed before prediction with:

```text
ERROR: --target-epitope-residues is a nanobody CDR-contact control; use template YAML constraints for --workflow protein.
```

The GUI had itself written `target_epitope_residues` and the nanobody-specific
`pocket+cdr3` mode into that protein-workflow template. Its recorded command also
contained `--model v2-flash` and `--post-iptm-threshold 0.70` despite having no
post-predictor. This exposed drift between the Swift form, command builder,
template schema and vendored runner rather than one bad flag.

## What was done

The complete iterative path was traced from `DesignFormView` through
`DesignRequest`, `TemplateWriter`, `CommandBuilder`, the durable manifest and
`nanohunter_run.sh`, including every predictor/checker and sequence-designer
branch. The following faults were fixed.

1. **One hotspot input, contextual restraint.** The template now writes
   `boltz_contact_mode: auto`. The runner resolves it to `pocket+cdr3` for a
   nanobody (generic binder pocket plus a CDR3-centre contact), and `pocket` for
   a generic mini-binder or peptide. Old Studio protein templates containing
   `pocket+cdr3` are accepted with an explicit compatibility warning and mapped
   to the equivalent pocket restraint.
2. **Hotspots cannot be ignored.** A hotspot request requires Boltz as the design
   engine and enables potentials. The form reconciles the engine and explains
   why; the runner fails rather than warning and continuing under an engine that
   cannot honour the restraint. Invalid residue tokens now block Start and make
   template writing fail instead of being silently dropped; Studio also rejects
   binder-chain (`A`) residues because its generated target is always chain B.
3. **Thresholds mean what the label says.** `hitThreshold` now emits
   `--iptm-threshold`, which controls campaign hit classification, as well as the
   post-check gate when that gate exists. Before this change the visible 0.70
   value only emitted `--post-iptm-threshold`; a no-checker campaign silently
   classified hits at the runner default 0.80. Failed old no-checker manifests
   recover their otherwise-unused post threshold as the campaign threshold.
4. **Checking is final and orthogonal.** Studio now emits `final` or
   `final-iptm`, implemented by a small independently testable task selector.
   It no longer re-folds every eligible intermediate cycle while describing and
   estimating the work as final-design validation. A design engine cannot check
   itself, duplicate backends are collapsed, and the design-only
   `Boltz + potentials` variant is no longer offered as a checker. Changing the
   design engine moves the former driver into checking instead of silently
   deleting the only independent check.
5. **Models are scoped.** `--model v2-flash|v2` is emitted and validated only
   when iterative IntelliFold PyTorch is the design engine or a checker.
   IntelliFold JAX remains outside this runner and is available in Predict and
   RFdiffusion3. AlphaFold 3 and OpenFold-3 have no IntelliFold model flag.
6. **AlphaFold 3 checking gets a real identity.** The runner's post-output name
   mapping omitted AlphaFold 3, producing `post_` paths and empty summary
   suffixes. It now uses `post_alphafold3` consistently.
7. **Boltz schemas stay with Boltz.** Design constraints are removed from every
   post-prediction input, and affinity properties are removed from non-Boltz
   inputs. Specific-atom ligand pocket controls require a Boltz design engine;
   P(bind) remains available when Boltz is either the design or checking engine.
8. **Every random choice is recorded.** The launch seed is routed to
   ProteinMPNN-family `--mpnn-seed`, AntiFold `--antifold-seed`, or the new
   `--lasermpnn-seed` as appropriate. De-novo cycle-0 generation receives the
   same recorded base as `--binder-random-seed`. A wrapper seeds Python, NumPy
   and PyTorch before executing upstream LASErMPNN, whose CLI has no seed option.
9. **Dependencies match hidden routing.** A protein campaign driven by
   AlphaFold 3 also declares Boltz, because the runner uses Boltz's native MSA
   path to prepare the A3M that AF3 consumes.
10. **Multiple checking engines remain visible.** Live validation identity now
    includes the predictor. Previously two checkers evaluating the same
    run/cycle collided and the second result disappeared. Dashboard language no
    longer hard-codes Boltz as the design engine or IntelliFold as the checker;
    its unique-design count explicitly means passing at least one check.
11. **Commands contain only relevant controls.** No-checker runs omit the post
    threshold and non-IntelliFold runs omit `--model`; non-Boltz design engines
    omit Boltz potential flags. The planning estimate now counts cycle 00 plus
    every requested optimisation cycle and at most one final check per engine.
12. **Known-missing components block Start.** Once component detection has
   completed, the form names missing engines/designers and prevents a launch
   that is already known to fail. A missing checker restored from an old project
   can still be turned off; the unavailable toggle only blocks turning it on.

The resulting iterative model roles are:

| Role | Available engines | Context |
|---|---|---|
| Design loop | Boltz-2, Boltz-2 + potentials, IntelliFold PyTorch, AlphaFold 3 | Boltz potentials are design-time steering; hotspot/atom restraints require Boltz |
| Final independent check | Boltz-2, IntelliFold PyTorch, AlphaFold 3, OpenFold-3 | Never repeats the design backend; never applies steering restraints |
| IntelliFold architecture | v2-flash or full v2 | Appears only when iterative IntelliFold PyTorch is actually selected |
| IntelliFold JAX/MPS | not in iterative runner | Remains in Predict and RFdiffusion3, whose adapters support it |

## Results

No performance measurements — contract audit, implementation and correctness
testing only.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Framework-free Swift production-source harness | 1 suite | command/template/model/dependency/multi-check assertions | pass |
| Isolated fake-install CLI suite | 1 suite | protein + nanobody hotspot routing, no-checker legacy threshold, AF3/IntelliFold checks, self-check rejection, final task selection | pass |
| Original failed command on the newly staged managed runner plus `--check-config` | 1 | configuration acceptance | pass |
| `bash -n` + Python compilation | 1 | syntax/import compilation | pass |
| `swift build` under `caffeinate` | 3 | production build | pass |
| Release `.app` build + strict code-signature verification | 1 | bundle validity | pass |
| Background app launch and managed-pipeline staging | 3 files | byte-for-byte source/staged comparison | pass |

The exact old template reported `contact_mode=pocket` rather than failing, and
its irrelevant `--model v2-flash` reported `intellifold_model=unused`. The
backward-compatible no-checker threshold path reports `hit_threshold=0.70`.
The background-launched release app staged the fixed runner and both new helper
scripts into `~/.iproteinstudio`; all three matched the bundled source exactly.

The installed Command Line Tools distribution advertised Swift 6.3.3 but
provided neither `XCTest` nor the `Testing` module. The regression suite therefore
uses a framework-free executable harness compiled directly with the production
sources; the initial framework attempts failed at module import and are not
counted as tests.

## Decision and rationale

**Keep one high-level hotspot concept.** Asking a bench scientist to understand
that a nanobody needs a CDR contact while a mini-binder needs a pocket constraint
would expose an implementation detail as a scientific choice. The workflow
already knows the binder type and can lower `auto` deterministically.

**Fail rather than ignore an requested restraint.** Continuing under
IntelliFold/AF3/OpenFold after dropping hotspots would produce a valid-looking
but scientifically different campaign. Engine reconciliation in the UI and a
runner error provide defence at both boundaries.

**Use final-cycle orthogonal checks.** The form, estimate and scientific purpose
all described checking the resulting designs. Checking every intermediate cycle
multiplied cost and changed the data set without exposing that choice. Legacy
CLI `all` and `iptm` modes remain available; Studio uses explicit final modes.

**Do not make IntelliFold JAX look interchangeable with PyTorch.** The iterative
runner has no JAX route. Emitting a model name is not enough to create one, so
the GUI continues to expose JAX only where a validated adapter exists.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

bash -n Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh
PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-pycache \
  python3 -m py_compile \
  Sources/iProteinStudio/Resources/pipeline/scripts/select_post_tasks.py \
  Sources/iProteinStudio/Resources/pipeline/scripts/run_lasermpnn_seeded.py

caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh

SDKROOT="$(xcrun --sdk macosx --show-sdk-path)" \
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-contract-clang \
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /private/tmp/iproteinstudio-iterative-contract
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract

SDKROOT="$(xcrun --sdk macosx --show-sdk-path)" \
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift-cache \
caffeinate -dimsu swift build
```

## Limits and what was not tested

- The original failure was replayed through full config/dependency validation,
  but no new iterative GPU campaign was launched. A real 4 × 6-prediction job
  would be expensive and was not necessary to prove the preflight fix.
- The new final-task selector was exercised with multi-run/multi-cycle fixtures.
  A complete real multi-check campaign using two post-predictors was not run.
- AlphaFold 3 and IntelliFold post routes reached real installed dependency
  validation plus isolated output-name checks; no new AF3/IntelliFold fold was
  launched in this entry.
- The LASErMPNN seed wrapper compiled, but a real LASErMPNN inference was not
  rerun. Falsification would be two fresh runs with the same manifest seed
  producing different FASTA output under identical installed weights/code.
- The form compiled, but the engine reconciliation and new explanatory copy did
  not receive a complete VoiceOver or keyboard-only pass.
- No performance claim or benchmark was added.

## Next

Run one deliberately small, real mini-binder campaign with a hotspot and two
final checking engines, interrupt it once, then confirm that Resume produces the
same cycle-0 sequence, final-check task set and dashboard rows as an uninterrupted
run.
