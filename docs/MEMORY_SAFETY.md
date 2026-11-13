# Memory admission

The native app now shows a per-run fitted RAM estimate with Proceed/Cancel before
queueing new work; see [Memory estimates](MEMORY_ESTIMATES.md). It uses a saved
explicit override only after the user confirms that exact run. Unmatched profiles
remain clearly unknown. CLI/MCP admission still checks at planning and dispatch;
`predict_batch.py` checks before MSA work and each engine stage, including direct
CLI use. All routes retain the same broker and memory sampling.

The estimate is a conservative screening policy, not a guarantee against every
allocation spike, driver failure, or change in another app's usage after start.
Sampling records actual process counters; it is not a runtime watchdog. Raw scientific scripts outside the broker and
the prediction batch runner do not acquire this policy automatically.

## Optional override and measurement

New app submissions ask for confirmation per run instead of using the global
override toggle. The review includes installed RAM, maximum complex size and
matched profile estimates with uncertainty. Cancel queues nothing; Proceed is
bound to the saved plan and review digest. Queued/resumed jobs keep their original
policy. A previous global preference does not suppress the new confirmation.

MCP scientific planners accept top-level `"memory_policy": "override"` (default
`"enforce"`), including recipes and engine batches. The bridge records this in
`normalized_request`, preserves the ordinary estimate or refusal as
`would_be_status`/`original_message`, and records `status: "overridden"`.
Unknown memory demand remains null. Overriding does not qualify an estimate.
The frozen worker propagates its recorded policy to prediction subprocesses;
it never reads the current GUI preference. Direct `predict_batch.py` configs
may also set `memory_policy`; the managed worker's saved policy takes precedence.

The override applies to memory admission, including insufficient available RAM,
unknown counters and uncalibrated inputs. Model availability, scientific input
validation, requested MSA provenance, immutable digests, process ownership,
shared execution lock and existing scheduling remain in effect. New plans are
required to change an existing job's policy; saved plans are never rewritten.

Managed commands sample their verified process tree approximately once per
second into unique `memory/*.jsonl` files under the job registry. Job status
exposes the latest `memory_samples` and `memory_summary` paths. Each command
and resumed attempt has a separate file. Records include stage, per-process
Darwin `ri_phys_footprint`, RSS, installed RAM, system pressure and system swap.
Summaries include sampled peaks, completeness, errors, OS/architecture, policy,
command and exit status; the enclosing immutable plan binds engine/runtime code
and scientific settings. Unreadable counters stay null, not zero. Abrupt
termination may leave a partial log without a finished summary.

Accounted footprint, RSS and GPU allocator values are distinct; do not add
them. Shared pages may be counted more than once in process-tree sums. System
swap/pressure includes other applications. Sampled peaks can miss transients.
These observations are calibration evidence, not automatic new memory limits:
qualify bounded workloads under Validation with manifests, raw-output audits,
replicates and runtime/hardware fingerprints before changing profile ranges.

## What is covered

The initial profiles cover Boltz, IntelliFold Flash/Full, OpenFold3 MLX,
ESMFold2 Fast/Full MLX and Protenix v2/Mini/Constraint. The Constraint profile is
available to shared design contracts; this does not add a new Predict selector.
Supported inputs are one or two ordinary protein chains, at most 916 residues
in total (370 for Protenix v2), without templates, potentials or affinity.
MSA-enabled inputs require an explicit cap no greater than 128; single-sequence
inputs and ESMFold2 Fast do not need that cap. Smaller inputs retain the fixed
model-loading allowance. Larger inputs are not extrapolated.

**Unqualified modes are blocked by default.** This includes RFdiffusion3, ligand NISE,
ligand/nucleic-acid predictions, larger assemblies, and guided predictions.
Boltz design normally enables partner potentials; those designs are therefore
blocked too. Nothing silently disables potentials, shortens sequences, changes
models, caps an uncapped MSA or lowers scientific sample budgets.

For eligible Protein Hunter plans, the check uses the maximum requested binder
length, target chains, initial and refinement model variants, independent
checkers and explicit worker count. It conservatively charges all selected
models as potentially resident together plus a 4 GiB CPU-work allowance.
Automatic concurrency calibration is blocked: an oversized first calibration
prediction is not a safe way to discover memory demand.

Experimental replay/validation routes are outside this production policy.
Already-running workers are not modified. Saved jobs made before the current
profile must receive a new checked plan; old scientific settings and completed
outputs are preserved rather than rewriting an immutable plan in place.

## Calculation and evidence

The CPU-only contract is `scripts/memory_admission.py`, with versioned data in
`memory_profiles.json`. The ordinary worker envelope is:

```
raw GiB = fixed loading cost + quadratic coefficient × tokens²
          + triangle score bytes × tokens³ / 2³⁰
required GiB = (raw × atom factor × 1.30 + 1.0) × concurrent samples
```

Pair and triangle shapes motivate the terms. The unchunked FP32 score allowance
is deliberately retained even where an implementation may chunk. Fixed costs
and nonnegative quadratic residuals envelope maximum sampled loading/request
footprints from Lab Books 0241/0245/0299: 35 historical conditions, five warmed
seeds per condition, one M4 Max with 64 GB unified memory. Protenix v2's failed
large input and separately repaired/chunked condition are not merged.

Atom counts use standard residue heavy atoms plus terminal oxygen, treating X
as the largest standard residue. The atom factor is at least one and otherwise
the squared ratio to seven heavy atoms per token, below every calibration
protein's density. This is a policy allowance for atom-dependent workspace,
not a claim that the entire model follows that law.

Directory batches reuse a model sequentially; they are not tensor batches.
Predict charges the largest concurrently runnable chunks in each token bucket,
then the largest engine stage. Seeds and sequential job counts do not multiply
the peak. Diffusion samples conservatively multiply the entire worker envelope,
including the existing five-sample Protenix default.

The preview reserves the greater of 4 GiB or 20% of physical RAM for the system.
Dispatch also limits the budget to free + inactive + speculative pages minus
2 GiB, and refuses elevated/unknown memory pressure or unavailable counters.
Above-budget inputs block; estimates above 80% of the budget warn. These margins
are engineering policy, not measured guarantees. Accounted footprint, RSS,
GPU allocations and swap must not be added together as physical RAM usage.

Plans retain the derived workloads and profile/calculation/planner digests. A frozen worker rechecks
against its current host before engine loading. Admission errors reach the GUI
through the existing submission/job failure channel.

## Validation and limitations

`Tests/test_memory_admission.py` exercises bounds, copies, atom composition,
variants, concurrency, samples, missing counters, unsupported modes, native/MCP
agreement and queued memory changes before execution. Queue/provenance suites
use inert workers with explicit synthetic memory workloads.

`Validation/experiments/memory_admission_v1/audit_profiles.py` reproduces coefficients from the
existing memory export without loading any model. This is retrospective
coverage of calibration data, not independent validation. Sampling may miss
transients; hardware/runtime differences and long resident sessions remain
unqualified. Promoting new domains or relaxed calibrated limits requires bounded validation
and Lab Book entries; explicit user overrides do not promote those limits. No installed app or active campaign is changed merely by
editing these repository sources.
