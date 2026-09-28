# Live resource monitoring

Open a job's **Job progress** window from the queue to see **Live resources · this Mac**. The same panel is used for Protein Hunter, NISE, RFdiffusion3 and Predict. It continues sampling even when the job service reports an error.

The panel updates approximately every two seconds while the window is open:

| Reading | Meaning |
| --- | --- |
| RAM used | Estimate of physical memory in use, excluding reclaimable file cache and purgeable pages. Compressed memory is included, not added again. Values use GiB. |
| Memory pressure | macOS's reported Normal, Warning or Critical condition. High RAM use alone does not imply a problem. |
| Compressed memory | Physical RAM occupied by the compressor. |
| Swap used | Disk space currently occupied by swapped memory. It can stay allocated after pressure eases. |
| Swap writing rate | Bytes written to swap between samples, displayed as MiB/s. This measures writes, not reads or general disk activity. |
| GPU activity | Whole-device utilization reported by the graphics driver, when available. This includes other apps. |
| CPU activity | Usage across all CPU cores, normalized to 0–100% of total capacity. |
| Thermal state | macOS's reported thermal condition. It is not a temperature measurement. |

These are **this Mac's totals**, not measurements attributed to the selected job or a remote computer. Apple Silicon uses unified memory: CPU and GPU memory must not be added together as separate physical pools. Resource readings help diagnose pressure; they cannot by themselves establish inference progress or predict completion time.

Expand **Recent RAM and GPU history** to see recent percentages. History retains up to 150 samples (about five minutes with normal scheduling) during this window's lifetime. **Copy support report** includes the sampled history and timestamps, without adding sequences or raw logs. Closing the window stops sampling; there is no persistent background telemetry or automatic upload. Viewing a completed job shows current Mac resources, not reconstructed historical readings for that job.

Missing counters display **Unavailable**. The first CPU and swap-rate reading needs a second sample. Delayed updates are labelled with their age. Sampling is separate from broker/log polling, runs off the UI thread, and does not launch `ps`, `powermetrics` or request administrator access.

## Implementation and portability

RAM/CPU counters come from Mach host statistics; swap and pressure from read-only `sysctl` queries. GPU activity comes from the optional IORegistry `IOAccelerator` → `PerformanceStatistics` → `Device Utilization %` property. Driver properties are not a stable Metal utilization API and may be absent on another OS/GPU. Multiple accelerator entries are treated as unavailable rather than combined into an invented utilization percentage. Missing counters never silently become zero/Normal.

Apple documents memory-pressure notifications in [DispatchSourceMemoryPressure](https://developer.apple.com/documentation/dispatch/dispatchsourcememorypressure) and the OS notification semantics in its [XNU source](https://github.com/apple-oss-distributions/xnu/blob/main/doc/vm/memorystatus_notify.md). This panel reads the current pressure level; it does not infer pressure solely from free RAM or use the app's own Metal allocations to represent another process's GPU usage.

This UI feature does not fix or alter job-supervision timeouts, inference settings, concurrency or campaign calibration.
