---
entry: 0559
title: Integrate RFD4, design search and Full CDR initialization
date: 2026-10-26
author: Codex
type: implementation
status: complete
machine: Apple Silicon Mac, 64 GiB unified memory
tags: [rfd4, esmfold2, search, app, packaging]
---

## Context

User requests app integration of the accumulated RFD4 code and pipelines, Full
CDR X-token initialization, beam search, and an inventory of other work not in
the app. Existing unrelated working-tree changes are retained. No production
campaign or public release was requested.

## What was done

Inventory: RFD4 currently exists in Validation experiments, with no Swift engine
or installer entry. NISE already exposes ligand beams; protein/nanobody fixed,
iterative and beam campaigns remain experimental controllers. Full CDR starts
completed in the private SUMO study (0314/0372) but public adapters still rejected X.

Added a narrow recorded CDR contract to the Full input parser and real Hunter YAML
writer, scoped to cycle 00. Public complete-sequence and Fast restrictions remain.
Connected nanobody choice in Swift and CLI/MCP stage validation. Five new CPU
tests exercise real writer/parser, framework preservation, target-chain X rejection,
masked MSA requirements and routes; ten existing epitope/handoff tests pass.
Default system Python lacks PyYAML; used the installed ESMFold2 interpreter.
One initial test assertion needed canonical /private path resolution on macOS.

Swift build passed with module caches redirected to /private/tmp and SwiftPM
sandbox disabled. Initial ordinary build was blocked by module-cache filesystem
permissions; no source compilation failure occurred.

RFD4 packaging found the experimental interpreter is framework Python3.12.10.
Downloaded matching standalone Python into the repository build area; did not
replace the user's existing executable. Extended the runtime packager to relocate
path-only editable loaders only when their source is explicitly vendored.
Runtime-v2 built with pinned native/prep/Diffusers sources, passed relocated imports
in a path containing spaces/Unicode, and excludes model weights. Native-model
import passed. CPU feature audits passed for the pinned protein, ligand, motif,
partial-diffusion and inverse-folding examples. Native authoring exposed a relative
path duplication; destination normalization was fixed and the authoring check is
being repeated. These checks do not qualify learned generation.

RFD4 integration modules under pipeline/scripts/rfd4 are under development.
They retain native condition authoring, separate native/prep processes, saved
per-unit receipts, upstream schedule, and exact-output qualification for optional
Metal adapters. General family-local search retains all proposals and explicit
selection ancestry. The native RFD4 form, managed planner, engine registry, result/history discovery
and typed MCP/CLI route are now present. Swift build passed after the initial UI
addition. Four CPU tests exercise search counts, ancestry, all-candidate retention,
interruption/resumption, tamper rejection, request validation and restricted editable
loader relocation. These modules are not yet deployed or end-to-end qualified.

## Results

No new scientific measurements. Existing experiment results are evidence for
porting behavior, not a performance claim for the new app integration.

## Decision and rationale

Preserve two distinct search mechanisms: outer sequence/refold search and native
RFD4 rollout search. Do not relabel either as the other. No arbitrary source-path
or weight dependency may remain in shipped runtime code. No retrospective
allocation threshold is silently promoted to a default.

## Reproduce

Run Tests/test_esmfold2_cdr.py and Tests/test_hunter_epitope_guidance.py with the
existing managed ESMFold2 Python. Build with CLANG_MODULE_CACHE_PATH,
SWIFTPM_MODULECACHE_OVERRIDE and SWIFT_MODULECACHE_PATH set to a writable scratch
directory and `swift build --disable-sandbox`.

Runtime preparation logs: /private/tmp/studio-rfd4-package*.log; build artifacts
under build/rfd4-integration. These are local qualification artifacts, not releases.

## Limits and what was not tested

Integration ongoing. No new learned inference, public distribution, installed-app
replacement, GUI acceptance, production memory soak or commit. Full CDR tests do
not replace an end-to-end packaged smoke. Native RFD4 rollout interruption and
broader conditioning modes require explicit qualification.

## Next

Finish runtime, planner, UI/results and search integration; test CPU contracts,
managed smoke/resume behavior and app build; update this record with outcomes.

## Integration acceptance update

This update supersedes the early in-progress status above. Base commit is
`be39339628202146c29fdd8809c23db491cdc6d2`; immutable broker snapshots record the
actual dirty source used for each test. Unrelated work is preserved.

The app now exposes eight RFD4 tasks, native condition authoring, imported starts,
fixed/iterative/greedy/beam sequence-refold search, and the separate pinned native
RFD4 rollout beam. It has managed planning, exact budgets, source/model/runtime
receipts, recursive completion verification, history/results and candidate exports.
Protein contigs are derived. SolubleMPNN is the protein default; AbMPNN preserves
nanobody frameworks. Missing inputs and failed audits stop the run. Optional pair
kernels require exact first-input equivalence. Large campaigns complete one
end-to-end family before expansion. RFD4 memory estimates remain uncalibrated and
require the visible explicit override. Scientific feedback has no inferred
independent hit verdict. Exact ligand chemistry is audited before scoring.

Portable CPython 3.12.10 runtime-v3 manifest:
`76c0212fbc81440124fd5a0485f6736a2d10d27445422a60413de7bc8fac7c13`.
Native source `2db07bb444d91695f8c10e6acb7648e9297f9221`, prep
`c9959efdebd75ac7fe9129fbbf0e291a6e0487d5`, Diffusers
`3421fed4a1655508436a5ca0c5179e88b0ec0afd`. Native model revision
`a06e2509c7033b010fc43614e9fd840303588502`; Diffusers model revision
`92fc3ae50e336b2ec59c713c19cfd43e5d3e923b`. Weights are separate and not
committed or embedded in app/runtime packages. Runtime-v2's relative `.pth` path
failed through a compatibility symlink; v3 uses a local source directory symlink
and a simple `.pth` basename. Relocation/imports now pass with spaces/Unicode and
the installed compatibility path. Old packages and failed runs remain preserved.

Validation Lab0251 declares the technical campaign. Completed live checks include
a 64-residue monomer, SUMO protein binder, partial diffusion, inverse folding,
motif scaffolding and exact reference/pair-kernel tensor equality. Outer beam
completed six predictions across two cycles. Cancellation after five completed
predictions and broker resumption reused their receipts and the sixth saved
sequence. This technical request explicitly retained all twenty amino acids;
the shipped default excludes C as in the qualified port. Full CDR initialization
completed cycle 00 and one AbMPNN/Full optimization cycle. Cycle 00 is a starting
structure, not an optimized design. Native ligand beam and the final derived
audit are pending at this update.

Seven RFD4 contracts, two real-upstream native-beam adapter tests, five CDR tests,
ten existing epitope/handoff tests and all Swift request/results harnesses pass.
The MCP suite passes all 24 tests with macOS memory-reading access; the initial
sandboxed run failed closed because it could not read installed memory. Monomer,
protein and outer-beam ZIP exports passed sequence, manifest and artifact checks.

Both `swift build --disable-sandbox` and `bash build_app.sh debug` pass. The local
ad-hoc-signed bundle is `build/iProteinStudio.app`, version 0.2.26/build 72, with
public updates disabled. It launched and showed the RFD4 selector and Full
nanobody option. Subsequent GUI inspection was blocked by the computer-use service
reporting “native pipe closed before response”, including reconnect. Full RFD4
form interaction is not claimed as visually verified. No app crash report found.

Retained failed attempts: monomer export required unavailable Bio; the ligand
oracle required unavailable biotite in the Boltz environment. Both handoffs now
use a dependency-free residue map, tested under Python without site packages.
Native beam attempt 02 completed four oracle predictions but exposed NISE's
campaign-relative receipts; verification now requires a recorded campaign root,
with recursive tamper coverage. Motif selections require native `[1-8]` range
syntax. Full CDR attempt 01 was blocked by live memory admission; attempt 02 used
a JSON test template where the shell reader required conventional YAML. Corrected
immutable requests retain all failed evidence. The bounded memory override is
declared in the campaign amendment, not silently enabled for future campaigns.

Reproduce with Tests/test_rfd4.py, Tests/test_mcp_bridge.py and
Tests/run_swift_contracts.py. CDR/epitope tests use the managed ESMFold2 Python;
Tests/test_rfd4_native.py uses the pinned RFD4 Python with native PROJECT_ROOT
and DEBUG=false. These contracts do not load model weights. The experiment's
audit.py verifies saved learned outputs without inference. Scientific reruns must
use the frozen broker plans and shared execution lock.

No throughput/efficacy claim, default promotion, public runtime release,
Applications replacement, or production memory soak. Not all native conditions,
predictor combinations or learned nanobody generation profiles were qualified.
The paired multi-cycle inverse/refold controller, retrospective adaptive depth
allocation and other experimental scheduler/Metal changes remain research work.
See docs/research/STUDIO_INTEGRATION_AUDIT_2026_10.md for the full inventory.

## Final acceptance

Native biotin beam attempt 03 completed all ten rollouts: four at each search
checkpoint and two terminal outputs. Exact reward formulas, generated and oracle
structure hashes, nested prediction receipts and completed-family replay pass.
The native export preserves ten sequences, all twenty generated/oracle artifacts,
source manifests and absent independent hit verdicts. The final audit also verifies
the six outer-search sequence/prediction units and parent identities, 29 mutable
CDR positions with fixed framework/target, masked MSA identities, two Full
predictions (one optimized design), and exact pair-kernel tensor equality.

Final evidence: Validation/output/studio_rfd4_integration_v1/run_20261026/
output-audit.json, broker-index.json, bundle-integrity.json and verification/.
All 68 checked bundled adapters/schemas match current source. Managed detection
reports RFD4 and both ESMFold2 profiles ready. No further code changes followed
the passing final build. Public release and the GUI automation limitation above
remain outside the completed local integration acceptance.

Production queue restored through the broker after tests: job-b3e3f8606412 is
running under its original plan, and job-4df41f91d918 is queued behind it. Both
report no error. Receipts are in the validation evidence's queue-restored.json.
