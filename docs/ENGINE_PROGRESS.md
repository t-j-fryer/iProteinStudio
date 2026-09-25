# Engine progress logs

New managed app/MCP jobs include engine progress in their main `pipeline.log`,
returned by MCP `job_status.pipeline_log_tail`. Messages also appear on the
engine's stderr, normally saved in its prediction/worker log. Mirroring to the
main log makes progress available even when an intermediate launcher captures
ordinary child output until exit.

| Engine | Observed milestones |
| --- | --- |
| Protenix v2, Mini and Constraint | Runner/model initialization, prediction, template embedding, MSA module, pairformer, denoiser calls |
| Boltz 2 | Prediction batches, MSA module, pairformer, diffusion sampling/denoiser calls, confidence |
| IntelliFold Flash and full | Prediction, trunk iterations, diffusion sampling/denoiser calls |
| OpenFold 3 MLX | Prediction, trunk, diffusion sampling/denoiser calls |
| RFdiffusion3 MLX | Backbone batch and denoiser calls |
| NESSO | ESM embeddings, scoring, pairformer calls |
| PSICHIC | ESM embedding batches and CPU graph batches |
| ProteinMPNN, SolubleMPNN, LigandMPNN, ABMPNN | Sequence sampling calls through their shared ProteinMPNN implementation |
| LASErMPNN | Sequence sampling |
| AntiFold | Sequence scoring |

The model variant, settings and input identity remain in the existing job records.
Shared implementations use a family label in progress records; ESM is labelled
`esm` for both screening engines. The PID distinguishes concurrent workers.

## Reading the records

The in-app **Progress & logs** viewer presents these events and offers job-specific
recovery controls. See [Jobs: progress viewer and cleanup](JOB_QUEUE.md#progress-viewer-and-job-cleanup).

Each line begins `IPROTEINSTUDIO_PROGRESS` and contains an engine, UTC timestamp,
PID, stage and event:

- `host_enter`: execution reached a model method.
- `host_return`: that method returned; `elapsed_s` is its host wall time.
- `host_error`: the method raised; the original exception is still propagated.
- `heartbeat`: every 30 seconds while an observed call is active. Reports elapsed
  time and time since the most recent observed host entry/return. It explicitly
  says `compute_progress=unknown`.
- `hook_unavailable`: a runtime's expected class/method is missing. Its detailed
  logging needs adapting; this is not a scientific fallback or successful stage.

Call counts are cumulative per process and stage. They are **not percentages or
diffusion step counts**: guidance, chunking and batching can invoke the same method
several times per step. Denoising logs are limited to the first call and every
20th (RFdiffusion3) or 25th call; other observed stages log every call. Errors are
always reported. Idle resident workers do not emit active-computation heartbeats.

A GPU can execute asynchronously after a host return. These observers neither
synchronize the GPU nor evaluate MLX arrays, and do not claim GPU completion.
A heartbeat proves only that the reporting thread ran. Its absence is also not
conclusive: a native call holding Python's interpreter lock can block that thread.
Existing output validation and job completion records remain authoritative.

## Scope and reproducibility

The broker enables a job-scoped Python startup observer through its subprocess
environment. It installs no global Python customization and preserves a portable
runtime's existing `sitecustomize` if present. Only listed engine methods are
wrapped, lazily after normal imports; telemetry never imports unused engines.
The observers pass through the original arguments, result objects and exceptions,
without inspecting tensors, consuming random numbers or changing model settings.

The observer and bootstrap are retained with the job's pipeline snapshot. Existing
jobs using older saved code retain their old logging. Running processes are not
patched. Set `IPROTEINSTUDIO_PROGRESS=0` in the launching environment to disable
instrumentation for diagnostic comparisons. Ordinary scripts launched outside
the managed broker are not automatically instrumented.

The app's high-level stage labels and progress bar are unchanged; this feature
adds detailed logs, not an estimated prediction percentage.

Validation and limits: [Lab Book 0188](../lab_book/0188-add-engine-progress-logging.md).
