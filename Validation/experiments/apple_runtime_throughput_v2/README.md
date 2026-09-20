# This-Mac runtime and implementation screen

Follow-on to `apple_runtime_throughput_v1`. M4 Max, macOS26.6.1 only.
No Protenix Mini; CPU MPNN unchanged. No model reduction, diffusion-step reduction,
guidance removal or MSA substitution. This is exploratory screening, not a default
promotion or a release qualification.

`prepare.py` creates independent APFS clones of package/source files, rewrites
editable import mappings, downloads SHA256-verified official wheels and seals
all runtime bytes (excluding bytecode). Installed engine environments are not
changed. IntelliFold's version guard is extended only in the cloned helper;
each worker still asserts the exact requested version. Protenix's upstream
GPU/Linux dependency pins already conflict with its deployed Apple dependency
graph; these pre-existing conflicts and the experimental Torch pin deviation are
retained in the dependency reports. AntiFold's Torch pin deviation is also explicit.

`preflight.py ENGINE --stage smoke --start` freezes a narrow experiment through
the real Studio broker. All GPU work is serialized by its shared lease; worker
processes belong to the broker cancellation group. Completed blocks carry request
and file hashes. Incomplete attempts are retained. Failed scientific arms are
never silently substituted. Follow-up candidate experiments require a complete,
passing screen (direct comparison or independently audited matched-draw replay).
An independently audited baseline may be used to test an
implementation idea even when the runtime candidate fails; `--runtime baseline`
is explicit in the frozen block.

`--reuse-reference` is restricted to exploratory implementation screens and
requires a completed audited block with identical engine/runtime/seed/thread/case
fields. The completed receipt and every output are rechecked. This saves repeating
an expensive reference solely to reject an implementation idea; its older timing
is explicitly not a contemporaneous control, and cannot establish a promoted gain.

Initial process blocks contain one first-call warmup, then ubiquitin76 and SUMO96.
These are two inputs, not independent replicates for every atom or diffusion step.
NESSO uses acetate as a generic small-molecule fixture. RFD3 is unconditional at
the same two lengths through the installed NumPy featurizer, full200-step/recycle2
EMA/BF16 profile. AntiFold tests teacher-forced logits on fixed benign monomer
backbones with its custom-chain path; antibody-specific validation remains needed.
Protenix uses fixed-input model-resident replay here; its production cycle-wave
scheduler still needs separate whole-workflow validation. OpenFold uses its existing per-input model setup; timings include reloading and
are explicitly not persistent inference. Its matrix labels follow saved fields;
PDE is never called PAE.

`profile` marks synchronized diagnostic runs separately from headline timings.
MLX outputs are explicitly evaluated before timing a lazy operation. CPU process
time can exceed wall time with threads and cannot alone be equated with a CPU
critical-path fraction. NESSO process time excludes preprocessing child CPU time.

`analyse.py` runs in the v1 Boltz analysis environment (NumPy/Gemmi), verifies
completed file hashes, checks sequence/atom/count/finite contracts, confidence
and pair-error outputs and the prespecified practical margins. Runtime upgrades
can change RNG behavior: a failing same-seed coordinate comparison triggers
investigation, not a claim that the newer runtime is scientifically worse.
A dedicated generator diagnostic is separate from model predictions.

Implementation arms: smaller IntelliFold padding buckets; NESSO ESM backbone-only
output, and immutable standard-AA CCD parsing reused with cloned mutable RDKit
molecules; upstream Protenix diffusion invariant cache; RFD3 gathered sparse SDPA
with FP32 attention arithmetic and unchanged neighborhoods/bias/gate. Every arm
keeps weights, shapes requested by the user, model settings and output counts.

User-directed SUMO analysis uses the same baseline-defined pLDDT≥80 core after excluding fixture residues1–20 in both
outputs, with a minimum of20 residues. Flexible-tail coordinates remain a separate
diagnostic. An insufficient core is unassessable, never silently replaced by a
whole-chain gate. Raw outputs and original audits are retained. Analysis records
both policy and script hashes. `inspect_padding.py RUN` reconstructs saved
IntelliFold feature loaders on CPU to audit effective tensor shapes.

`tape` records/replays identical framework random draws for diagnosing runtime
arithmetic, not timing. `steady` warms both AntiFold shapes before repetitions.
`kernel` benchmarks existing/compiled MLX, SDPA and direct-load Metal attention
against an independent FP64 oracle; it is not a model throughput result.
OpenFold `attention` preserves the existing query scale in native Torch SDPA.
OpenFold `init` skips only checkpoint-overwritten Linear initializers and verifies
strict state coverage and exact loaded tensor values before any inference.

Run harness receipt tests with:
`python3 -m unittest discover -s Validation/experiments/apple_runtime_throughput_v2 -p 'test_*.py'`

See project Lab Book0169 and Validation0039 for outcomes, failures and untested cases.
