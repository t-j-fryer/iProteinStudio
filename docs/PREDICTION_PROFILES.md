# Prediction settings

New Studio jobs use the following prediction profiles. The app, MCP and CLI
read the same versioned defaults. These are speed/quality choices evaluated on
this project's Mac benchmarks, not universal accuracy guarantees.

| Engine | Maximum supplied MSA rows per protein chain | Diffusion steps | Recycles / trunk loops |
|---|---:|---:|---:|
| Boltz2 | 128 | 25 | 3 |
| IntelliFold Flash | 128 | 25 | 10 |
| IntelliFold Full | 128 | 25 | 10 |
| Protenix v2 | 128 | 25 | 10 |
| Protenix Constraint v0.5 | 128 | 25 | 10 |
| Protenix Mini | 128 | **5 (native)** | **4 (native)** |
| OpenFold3 | 128 | 25 | 3 |
| ESMFold2 Full | 128 | **100 requested (native)** | **20 (native)** |
| ESMFold2 Fast | **No MSA** | **50 requested (native)** | **3 (native)** |

An MSA cap includes the query and keeps the first rows in the supplied order.
Studio retains the original alignment and stages a checksummed capped copy;
it does not replace the shared MSA cache. A depth of zero preserves the supplied
alignment, subject to the engine's native feature/model limits. Designed binders
retain their explicit single-sequence policy. Nanobody scaffold MSA policies
remain independent of target alignment retrieval.

These profiles do not change sample counts, seeds, guidance, potentials,
affinity-head settings, sequence-design settings or RFdiffusion3 generation.
Those retain their existing separate controls. ESMFold2's API step counts are
requested sampler budgets, not a promise about the number of internal calls.

## Change settings

In Predict, Protein Hunter, RFdiffusion3 verification and NISE, open
**Prediction accuracy & compute** (under Advanced where applicable). Target Prep
exposes the same controls. Settings are per engine and apply when that engine
is selected. IntelliFold Flash and Full have separate profiles. Prediction
sample and seed counts remain in the existing sampling controls.

MCP prediction, target-preparation, NISE and RFdiffusion3 requests accept:

```json
"prediction_settings": {
  "boltz": {"msa_depth": 0, "diffusion_steps": 200, "recycles": 3},
  "protenix-mini": {"msa_depth": 128, "diffusion_steps": 5, "recycles": 4}
}
```

For the iterative CLI/MCP argument list, supply the same JSON with
`--prediction-settings-json`. An explicit native engine CLI sampling/recycle flag
continues to take precedence. Boltz affinity remains a separate model with its
own native settings. RFdiffusion3's generation steps/recycles are not prediction
steps/recycles.

Profiles are saved with results in `prediction_profile.json`; preflight preserves
code, profile defaults, inputs and runtime identities. Existing accepted jobs
resume their original frozen settings. To change science, create a new job.
Target Prep cache identities include the settings profile, preventing reuse of
a structure produced under a different requested budget.

## Runtime improvements

- IntelliFold uses exact input tokens by default. Explicit padding overrides are
  retained. Resident sessions cache the chemical dictionary, not joint features
  from a different binder.
- Boltz resident sessions retain their owned structure/affinity models on MPS
  between requests and release them when the worker exits.
- OpenFold's single-query preparation avoids loader-process startup and preserves
  worker-zero feature RNG. Multi-query batches retain their native loader policy.
  Reference conformer coordinates are read as arrays with the same atom ordering,
  float32 conversion, cropping and augmentation.
- Protenix Constraint uses its native within-prediction diffusion-conditioning
  cache. Protenix v2 and Mini keep their validated native compute path.
- ESMFold2 keeps its native model calculation and bounds the free MLX allocator
  cache at 4 GiB. This is not a limit on active model memory.

Rejected precision, Metal backend and ESM target-embedding experiments are not
enabled. Evidence and limitations are in [the shared-target study](../lab_book/0230-shared-target-paper-predictions.md)
and [release acceptance](../lab_book/0234-publish-prediction-profiles.md).
