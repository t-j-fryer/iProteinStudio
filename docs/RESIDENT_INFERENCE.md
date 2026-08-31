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
to macOS `MTLCompilerService`. The CLI mode exists for governed validation, but
the GUI continues to expose the established scheduler until promotion gates
pass.

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

## Promotion gates

A backend can become the default only after the paired full campaign in
`Validation/experiments/resident_design_v1` demonstrates a speed gain and all
of the following pass:

- exact 12 × 6 prediction output cardinality (cycle 00 plus cycles 01–05);
- exact submitted binder and target sequences and cached-MSA checksum;
- finite coordinates, complete backbones and required confidence outputs;
- identical job-local seed behavior under reversed input order;
- clean interruption, cancellation, worker-death and resume behavior;
- bounded unified-memory use across at least the complete campaign;
- no CPU execution except the separately counted known Boltz SVD fallback.

Until then, cycle-wave is an explicit experimental mode and the app must not
describe it as persistent or as a single tensor batch.
