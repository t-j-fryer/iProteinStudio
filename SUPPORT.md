# Support

iProteinStudio is alpha research software for Apple-silicon Macs running macOS
14 or later. It is not a clinical or diagnostic product.

## Before reporting a problem

1. Confirm that the app is in `/Applications` and that only one current copy is
   installed.
2. Open **Engines** and check whether the required engine is installed, complete
   and current.
3. Use the in-app **Show log** action for installation failures.
4. For an interrupted campaign, use its recorded Resume action rather than
   starting a different run with the same name.

Installer logs are retained under `~/.iproteinstudio/logs/installer`. Individual
campaign folders contain their own commands, provenance and stage logs.

## A GPU prediction appears stalled

Open the run log and note the last completed stage. Initial model loading can
take time; an unchanged progress indicator alone does not establish a GPU fault.
Use **Stop** before investigating or retrying the job. Retain its logs and saved
outputs. If multiple previously working engines hang, save work in other apps,
restart the Mac, then use **Resume** for the affected job.

Version 0.2.5 and later include **Progress & logs → Check & clean up…** in the
job queue and Activity/history. It can stop a live job or clean up identity-verified
leftover processes while preserving results. For an older job whose process
ownership cannot be established, follow the restart guidance in the viewer. To
adopt updated worker fixes, make a new submission after recovery; Resume keeps the
old job's code. See [job cleanup](docs/JOB_QUEUE.md#progress-viewer-and-job-cleanup).

If the problem persists, report the job ID and last log messages. Support can
request the [optional GPU-storage diagnostic](docs/PORTABLE_RUNTIME_IMPLEMENTATION.md#optional-gpu-troubleshooting).
Normal jobs do not run that diagnostic, and Studio does not automatically clear
shared Apple temporary files. Version 0.2.2 performed a per-job check; 0.2.3
removes it. A separately authorized repair and its limits are recorded in
[Lab Book 0178](lab_book/0178-repair-mps-scratch-stall.md).

## Asking for help

Use the GitHub issue tracker:

<https://github.com/t-j-fryer/iProteinStudio/issues>

Include:

- iProteinStudio version and build;
- Mac model/chip, memory and macOS version;
- workflow and selected engines;
- the exact visible error; and
- the smallest sanitized log excerpt that demonstrates the failure.

Do not attach model weights, AlphaFold 3 parameters, unpublished sequences,
confidential structures, API credentials or an entire project directory. Replace
local usernames and sensitive project names before posting logs.

Report security problems privately as described in [SECURITY.md](SECURITY.md).
