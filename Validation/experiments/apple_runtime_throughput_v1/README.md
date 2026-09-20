# Apple runtime throughput screening

Isolated, same-settings Boltz-2 controls before broader engine optimization.
MPNN stays on CPU. No production runtime/default changes. Scientific choices
(200 steps, three recycles, one requested sample, full potentials, FP32 and the
allocator reset) remain fixed. Two explicit empty-MSA monomers establish a
bounded functionality screen; they cannot establish interface/design accuracy.

`prepare_environments.py` makes independent APFS copies of the installed Boltz
packages and installs only the SHA256-verified official Torch 2.14 wheel into
the candidate. Both environments have dependency checks and full file seals.
These development copies are not relocatable release runtime packages.

`preflight.py --stage smoke --start` calls the shipped workflow guide, freezes
code/settings/seals/checkpoint and canonical amino-acid asset digests, persists
an immutable experimental desktop plan and calls MCP `job_start`. Execution
uses the real shared broker lease, cancellation group and resident adapter.
It never invokes model inference directly outside the broker. The factory has
fixed workloads, no arbitrary-command argument and no production MCP changes.

Each process runs one warmup followed by paired ubiquitin/SUMO measurements.
The first smoke compares Torch 2.13/2.14 at four CPU threads. After a passing
smoke, `--stage repeat` reverses runtime order at seed43, while `--stage threads`
tests candidate threads4/1/8/12 at seed42. BLAS/OpenMP and Torch thread budgets
match; interop=1, preprocessing=1 and data workers=0 isolate intra-op threading.
No simultaneous GPU workers. These settings are experimental, not defaults.

CPU-FP64 synthetic references check matmul/indexing before inference. The model
comparison uses the declared practical margins plus hard sequence, atom,
finite-output, cardinality and new-discontinuity gates. Existing baseline
violations are explicitly reported, never treated as proof of accuracy.
Warmups are excluded from throughput summaries but still numerically compared.
Native timings include preprocessing, inference, writing and geometry checking;
model loading is reported separately. A block's three inputs reuse one model.

Completed blocks have hashed receipts and are reverified on resume; incomplete
attempts remain untouched and restart as fresh processes. Runtime files are
verified against seals before inference. Only documented Boltz SVD CPU fallback
is allowed and counted in retained logs. No change is promoted by this screen.

Tests (CPU only):

```bash
Validation/output/apple_runtime_throughput_v1/environments/boltz-torch213/bin/python -m unittest discover -s Validation/experiments/apple_runtime_throughput_v1 -p 'test_*.py' -v
```

Remaining acceptance includes complex/interface metrics and rankings, larger
shapes, guidance-active workloads, baseline repeatability, memory soak, real
cancellation/resume, M1/M2/M3/M5 coverage and other engines. Practical thresholds
must be calibrated prospectively for those endpoints, not widened after failure.

`--stage profile` adds a separate synchronized diagnostic arm around input
embedding, templates/MSA, pairformer, diffusion conditioning/sample, confidence
and preprocessing. SVD dispatch shapes/devices are counted. The ordinary
reference arm comes first and all outputs are compared. Profile timings are
excluded from speedup claims because barriers can perturb overlap. CPU process
time is recorded in newer worker revisions; it excludes child validator CPU.
Each immutable plan retains the exact harness revision it used.

`--stage schedule` tests one implementation-only change selected after the
coarse profile: copy the already GPU-computed sigma/gamma schedule to the host
once instead of three scalar reads per diffusion iteration. GPU schedule
arithmetic, initial sigma tensor, all200 iterations, guidance and RNG calls are
retained. A source-anchor-checked method copy is bound only in the isolated
worker; no installed source is modified. The independent reference arm and
all practical output gates remain. CPU tests verify exact scalar/RNG parity.
No speedup is assumed; reject it if a worthwhile repeatable benefit is absent.

`--stage precision` is a separately declared approximate-arithmetic experiment:
BF16 autocast only around the diffusion score network, which dominates the
profile. Weights remain FP32; trunk, diffusion state/update, alignment, guidance
and confidence retain their original FP32 paths. Actual first-linear and score
output dtypes are recorded. This is an explicit exception to the baseline FP32
arithmetic profile, not a model/step/guidance change. The same practical output
margins are fixed before this arm. Passing small monomers cannot promote it.

Completed initial results and limitations are in Project Lab Book0168 and
Validation Lab Book0038. Regenerate derived output without rerunning inference:

```bash
Validation/output/apple_runtime_throughput_v1/environments/boltz-torch213/bin/python Validation/experiments/apple_runtime_throughput_v1/summarise.py Validation/output/apple_runtime_throughput_v1
Validation/output/apple_runtime_throughput_v1/environments/boltz-torch213/bin/python Validation/experiments/apple_runtime_throughput_v1/external_reference.py Validation/output/apple_runtime_throughput_v1
Validation/output/apple_runtime_throughput_v1/environments/boltz-torch213/bin/python Validation/experiments/apple_runtime_throughput_v1/audit.py Validation/output/apple_runtime_throughput_v1
python3 Validation/experiments/apple_runtime_throughput_v1/plot.py Validation/output/apple_runtime_throughput_v1
```

Plotting uses the existing system Matplotlib installation; scientific venvs
remain sealed. The optional1UBQ reference requires an explicit first download
(`external_reference.py ... --download`), then verifies its saved digest.
