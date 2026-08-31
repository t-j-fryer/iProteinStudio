# Resident iterative inference architecture

## Terminology

- **Per-trajectory**: one predictor process advances one trajectory through all
  cycles, reloading the model for every cycle.
- **Cycle-wave directory**: all ready inputs for one cycle are submitted in one
  predictor process. The model loads once per cycle, then the process exits.
- **Campaign-resident**: one predictor process loads the model once, accepts a
  sequence of cycle-wave requests separated by MPNN redesign work, and exits
  only when the campaign completes or is cancelled.

Directory replay with all future inputs already present is an upper-bound timing
assay, not campaign residency.

## Implemented validation contract

The shell runner remains the owner of trajectory state, MPNN calls, normalized
outputs and resume decisions. A resident predictor is a replaceable child
process with an atomic file-backed request/response queue:

1. startup fixes one engine, checkpoint, sample count, seed policy and scientific
   settings, asserts native MPS, loads the checkpoint and emits `ready`;
2. each request names an immutable directory of YAML inputs and a new output
   directory, plus an exact expected job count and request checksum;
3. the worker resets request-level RNG state, processes jobs in lexical order,
   verifies output cardinality and emits an atomic completion response;
4. the shell audits and copies each result into its trajectory/cycle before MPNN
   creates the next request;
5. malformed output, worker death, owner-process death or a checksum mismatch
   fails the campaign loudly. Resume starts a new worker and submits only
   incomplete cycles.

Model residency is an optimization, never a new source of campaign truth.

`scripts/resident_predictor.py` implements three model-owning sessions: Boltz 2,
IntelliFold PyTorch and Protenix. The six app engine choices map to those three
families and their fixed checkpoints. The worker remains a normal child of the
campaign process; double-fork daemonization was rejected after it severed access
to macOS `MTLCompilerService`.

New GUI campaigns select the measured optimized policy automatically:

- Boltz 2, IntelliFold v2-flash, IntelliFold full v2, Protenix Mini and
  Protenix Constraint use one campaign-resident worker;
- full Protenix v2 uses one cycle-wave process per cycle because its measured
  resident run was slower under sustained MPS load;
- Compatibility mode retains the historical per-trajectory process route for
  reproducing old campaigns and diagnosis.

## Engine-specific batching and padding

### IntelliFold PyTorch

IntelliFold pads each example to the smallest configured token bucket. The
current `auto` mode uses one bucket equal to target tokens plus the maximum
binder length. That is appropriate for fixed-length nanobody scaffolds. For a
96-aa target and 65–150-aa minibinders it pads every input to 246 tokens.

A resident mixed-length campaign should retain each trajectory's sampled length
across cycles and use a short, declared list of total-token buckets. Candidate
buckets must be benchmarked; more buckets reduce padded attention work but can
increase shape warm-up overhead. Exact per-length buckets are not assumed to be
optimal for only 12 trajectories.

The current speed campaign does not test this policy: all binders are exactly
80 aa and every IntelliFold arm uses the same 176-token bucket.

### Boltz 2 and Protenix

Their directory interfaces reuse one loaded model while iterating examples; they
are not a dense tensor batch padded to the longest directory member. Grouping by
length may improve allocator locality, but it does not remove a demonstrated
cross-example padding cost. Do not split a wave into extra model loads merely to
make artificial length buckets for these engines.

### Nanobodies

Fixed scaffolds have the same length, so token-aware scheduling adds no useful
partition. CDR sequence changes do not change tensor length.

## Validation and promotion decision

The paired 12-trajectory, five-cycle, 80-aa SUMO campaign completed for all six
engines and all three schedulers. Cycle 00 was audited but excluded from the
1,080 optimized design structures. Receipt-level cardinality and structure
audits passed. End-to-end wall time in minutes was:

| Engine | Per-trajectory | Cycle-wave | Resident | Selected policy |
|---|---:|---:|---:|---|
| Boltz 2 | 40.26 | 28.35 | **22.07** | resident |
| IntelliFold v2-flash | 47.01 | 38.52 | **38.05** | resident |
| IntelliFold full v2 | 170.35 | 153.63 | **151.04** | resident |
| Protenix v2 | 84.96 | **70.44** | 79.93 | cycle-wave |
| Protenix Mini | 20.39 | 4.94 | **4.54** | resident |
| Protenix Constraint | 66.43 | 42.65 | **40.09** | resident |

These values were measured on the M4 Max described in Lab Book 0046; they are
not estimates for other Macs. Model-load counts were 72, 6 and 1 for the three
respective scheduler arms.

Protenix v2 resident memory stayed bounded at 2.75--2.82 GB, but mean model
forward time increased from 55.30 s in cycle waves to 65.14 s in the resident
process. The benchmark did not record power or temperature, so thermal or MPS
process-lifetime effects remain hypotheses rather than claims.

The following broader promotion gates remain for extending this policy beyond
the validated fixed-length protein-binder route:

- exact 12 × 6 prediction output cardinality (cycle 00 plus cycles 01–05);
- exact submitted binder and target sequences and cached-MSA checksum;
- finite coordinates, complete backbones and required confidence outputs;
- clean interruption, cancellation, worker-death and resume behavior;
- bounded unified-memory use across at least the complete campaign;
- no CPU execution except the separately counted known Boltz SVD fallback.

Mixed lengths, ligands, nanobodies, post-predictor stages and other Apple chips
were not part of this benchmark. Residency is a process-lifetime optimization,
not a tensor-batching claim; output order can also affect an upstream engine's
RNG stream, so cycle-wave and resident scientific settings are held constant
but are not asserted to reproduce independently restarted per-input samples
bit-for-bit.
