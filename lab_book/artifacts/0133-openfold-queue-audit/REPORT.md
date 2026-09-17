# Studio queue and OpenFold-3 failure audit

Audited 2026-09-16. Workspace: **Bgx** (stored as `untitled_design`), target: **α-Cobratoxin**.

The geometry messages in the attachment are advisory records, not errors.
IntelliFold Full completed its 250 optimized structures and 50 starting structures.
The next engine, OpenFold-3, was given `--design-scheduler resident`; no OpenFold
resident worker exists, so the runner rejected the command before inference.

## Completed and outstanding

| Batch suffix | Saved settings | Completed optimized structures | Starting structures | Outstanding OpenFold-3 |
|---|---|---:|---:|---:|
| `6ed978fa` | Mini-binders, 65–150 aa, helix strength 0 | 1,500 | 300 | 50 trajectories × 5 cycles = 250 |
| `06751263` | Mini-binders, 65–120 aa, helix strength 1 | 1,500 | 300 | 50 trajectories × 5 cycles = 250 |
| `f45742c3` | Nanobodies, all three CDRs, AbMPNN, eight scaffolds | 1,500 | 300 | 50 trajectories × 5 cycles = 250 |
| **Total** | | **4,500** | **900** | **750** |

Each batch completed Boltz 2, Protenix Constraint, Protenix v2, Protenix Mini,
IntelliFold Flash and IntelliFold Full. The nanobody total spans 48 completed
engine/scaffold campaigns; each mini-binder batch spans six. These are saved
design-cycle structures, not counts of independently validated hits or unique
sequences. No orthogonal post-check was requested in these campaigns.

The eight outstanding nanobody scaffolds are Vobarilizumab (7 trajectories),
Caplacizumab (7), Gefurulimab (6), Ozoralizumab ALB8 (6), Gontivimab (6),
Isecarosmab (6), Sonelokimab (6), and NbBcII10 FGLA (6).

## Queue state

**Nothing is currently running or queued.** All three batch jobs failed at their
first OpenFold child, but the global queue continued to subsequent batch jobs.
The first batch failed September 10; the second September 14; the nanobody batch
September 16 (UTC). See [job records](jobs.json).

Three OpenFold campaigns failed before inference. Seven subsequent nanobody
OpenFold campaigns never started: their initial manifests say `running`, but the
parent failed at child 49 of 56 and there is no running worker or saved prediction
for those children. These are outstanding work, not seven active queue jobs.

Other recent desktop queue history includes a completed NISE job and two failed
NISE jobs in workspace `test2`; those are separate from this error and are
covered by [the earlier NISE audit](../0131-test2-nise-audit/REPORT.md).

## Verification and fix

Read the broker's `error` and `pipeline_log_tail`, run manifests, batch progress
receipts and the MCP result hierarchy. Verified all **49,256** recorded artifact
SHA-256 checksums, all summary run/cycle pairs, and every summary-referenced
structure's existence. There were no missing or changed recorded artifacts.
[Per-campaign CSV](campaigns.csv) and [audit totals](audit.json) preserve the count evidence.

Fixed the app command builder to use OpenFold-3's established `run` scheduler,
matching the existing MCP planner. Added native preflight rejection so an
unsupported OpenFold resident request fails before any engine in a batch runs.
The runner's fail-loud guard remains intact.

The rebuilt app is `build/iProteinStudio.app`, the same app location currently
running. Quit and reopen Studio to load the corrected executable. The current
running process still has the old executable loaded.

Existing frozen job plans and results were preserved. **Resuming an old failed
batch unchanged still reuses its invalid recorded command.** Recovery requires a
new preflight plan for only the ten unfinished OpenFold campaigns, preserving
their saved seeds, templates, MSAs and frozen pipeline and recording the change
from `resident` to `run`. Completed engines must not be resubmitted. No scientific
jobs were restarted during this audit.

## Test scope

Swift request/controller/result contracts passed; 18 desktop job tests passed;
10 engine-batch tests passed; the shell CLI contract passed; `swift build` and
local app bundle assembly/signature verification passed. The batch regression
executes inert workers and checks invalid final-engine preflight prevents every
earlier engine from starting. CLI checks invoke the actual runner's configuration
validation. No new model inference, scientific-quality assessment, or performance
benchmark was performed.
