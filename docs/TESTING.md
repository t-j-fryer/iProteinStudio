# Testing Studio

Run from the canonical iProteinStudio checkout:

```bash
python3 Tests/run.py --list
python3 Tests/run.py
```

The default `fast` suite invokes each Python file as a script, then the shell
contracts, `swift test`, and executable Swift harnesses. This matters: several
existing test files perform assertions in `main()` and importing them through
unittest discovery does not execute those checks. Any failed command makes the
runner fail. Its final report lists failures and acceptance work that was not run.

## Dependencies

Fast contracts require macOS, Python 3, Bash, Swift and a compatible SDK. The
XCTest target requires a selected full Xcode installation providing XCTest;
Command Line Tools alone can build the application and execute the standalone
Swift harnesses but may not provide XCTest. CI runs the full fast command on a
macOS runner. No engine, weights or Python dependencies are installed by the test
runner. Process-group and local bridge tests need permission to run local child
processes and bind a loopback port.

On a machine with an SDK/toolchain mismatch, select a compatible installed SDK
through `SDKROOT` and use `--scratch-path` for an isolated build directory. A
missing XCTest module remains a failed check; it is not silently skipped. To run
the executable contracts independently:

```bash
python3 Tests/run_swift_contracts.py
swift build
```

The standalone core harness executes recovery, archive rollback/crash replay,
exclusive lease and diagnostics-redaction checks without XCTest. Result and
iterative harnesses exercise file layouts, saved verdicts and command generation.
These supplement the standard test target.

Science fixtures require a prepared Python with the dependencies imported by the
selected scripts, including PyYAML, NumPy, Biotite, Biopython, RDKit and requests. Use an
existing suitable environment or prepare a separate test environment explicitly:

```bash
python3 Tests/run.py --suite science --science-python /path/to/test-env/bin/python
python3 Tests/run.py --suite all --science-python /path/to/test-env/bin/python
```

These are fixture checks, not model inference or benchmarks. New hardware runs
belong under a declared `Validation/` campaign with its required manifest/audit.

`test_initialization_refinement.py` preserves historical journal/library integrity
and checks that retired CLI proposal requests leave journals unchanged.
`test_monomer_initialization_pipeline.py` executes the actual per-run scheduler
with synthetic prediction/MPNN adapters and real Biotite coordinate assessment,
checking initialization-only handoff, ordinary cycling and idempotent resume.
The public CLI and MCP contracts reject beta, mixed, sustained and inspection
controls. These fixture suites make no real-model efficacy claim.

## Coverage boundaries

Fake-worker integration checks exercise native/MCP serialization, queued
provenance rejection, cancellation of a resistant descendant, fixed iterative
commands and saved RFdiffusion3 preparation. Temporary directories isolate these
from installed engines and existing campaigns. Source-based UI contracts verify
wiring only; they do not establish accessibility or usability.

`Tests/test_desktop_jobs.py` also submits inert jobs through all four native
workflow adapters and verifies shared-lock serialization, cancellation of queued
work without stopping another workspace, cancellation before worker startup,
and clearing cancellation intent on resume. `Tests/run_swift_contracts.py` runs
the actual four controllers with a mock job session to check observation
switching, independent saved runs, and duplicate-submission guards.

`bash Tests/test_ligand_atom_selection.sh` opens an isolated native SwiftUI test
window with pre-resolved ethanol atoms and the real bundled RDKit/WebKit viewer.
It drives the None/Bind/Expose control, checks stored choices and map identity,
independent atom selections, visible SVG layer ordering, stale-map disabling and
clear/reselect. It does not use installed engines, user workspaces or inference.

Before release, run the application and complete setup, Start, Stop, Resume,
workspace switching, archive/restore and result navigation using keyboard and
VoiceOver. Check enlarged display/text settings, focus order, control names,
contrast and reduced motion. Test crash/relaunch against fake jobs with an
isolated support root. Packaged resources, Gatekeeper, signing/notarization and
Sparkle updates have separate acceptance procedures and are not implied by a
passing `swift build`.

Do not overwrite the managed runtime beneath an active validation campaign to
perform GUI acceptance. Record exact commands, failures and omissions in the
project Lab Book. Never report fixture timing as an inference benchmark.

Initialization helix control (project0101): the active CLI/MCP and GUI emit only `--negative-helix-constant`, applied at initialization. The shell fixture checks ordinary cycling and idempotent resume; retired refinement CLI requests must fail. Journal/library tests preserve the ability to inspect historical experiments. The cross-engine campaign contract lives in `Validation/experiments/helix_strength_all_engines_v1/test_campaign.py`.


`test_nesso_screen.py` executes per-trajectory shortlisting, partial-screen
replay, corruption refusal, installation-state detection and the model-client
lifetime with synthetic scores. `test_nise_science.py` also runs the ported
search with beam two and screening, checking first-cycle/later-cycle sampling
and exact replay. These are fixture tests; they do not validate NESSO ranking
accuracy or establish a throughput improvement.

`test_apple_build_tools.py` executes the real C++ compile/link/run probe, missing
tool and compiler-failure fixtures, and recovery after tools become available.
`test_apple_build_tools_ui.sh` runs the real native installer controller with a
mock process boundary: it checks explicit Apple installer requests, failed
requests, preserved engine arguments on retry, and execution-lease release while
waiting. These checks do not open Apple's installer or establish fresh-Mac GUI
acceptance.

NISE atom identity tests need the **installed Boltz environment**, including its
actual parser and the installed ALA molecular dictionary. They execute Boltz
input parsing, per-atom solvent-accessibility calculations, failure filtering,
reordering/stale-map checks and request validation, without neural inference:

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" \
  "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_atoms.py
```

Run `Tests/test_nise_rfd3.py` in that same environment for the real ligand-preparation
handoff and conditioned/unconditioned resume fixtures. Model generation remains
stubbed. These installed-engine checks are separate from the generic fast suite.
