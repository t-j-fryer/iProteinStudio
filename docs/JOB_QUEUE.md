# Job queue

Protein Hunter, NISE, RFdiffusion3 and Predict use the same queue across every
workspace. You can submit another run while existing work continues.

1. Open the workspace and tab you want. If it shows an existing run, click
   **New run** above the tabs to return to the form with your workspace settings.
2. Complete the settings and click **Add to Queue**. When no work is active,
   the button retains its usual Start/Fold label. Missing inputs and unavailable
   engines must still be resolved before submission.
   You can enter an optional **Run name** beside the button in any tab. Each tab
   remembers its own draft name. Queue and Activity show the saved name; leaving
   it blank keeps the automatic name. Reusing a name creates a separate run and
   never overwrites earlier results.
3. Open the queue icon at the top right to see all running and waiting jobs.
   Each row identifies the workspace, workflow and saved run folder.
4. Use **Show run** to open a job's progress, or **Show files** to reveal its
   output. **Cancel** removes waiting work; **Stop** interrupts active work while
   retaining completed checkpoints. Activity/history provides supported Resume
   actions for stopped or failed work.

## Progress viewer and job cleanup

In version 0.2.5 and later, choose **Progress & logs** in the queue, or **Logs**
beside a run in Activity/history. The viewer refreshes every two seconds and shows
the latest engine stage, elapsed time, readable engine events, ordinary job output
and worker diagnostics. **Follow latest** can be disabled while reading. The
queue also lists recent finished, stopped and failed jobs so their diagnostics
remain accessible.

**Engine progress** explains the difference between computation milestones and
heartbeats. A quiet log does not prove a hang, and a heartbeat does not prove GPU
progress. The viewer shows the latest 500 job-log lines and 100 worker-log lines;
older saved jobs may only have ordinary logs.

For a job that needs attention:

1. Open its viewer and click **Check & clean up…**.
2. Review the explanation. For a live compatible worker, Studio offers Stop. For
   a crashed worker with recorded leftovers, it offers cleanup of those processes.
   A stale active state with no live recorded worker can be cleared.
3. Confirm **Continue & keep saved results**. Inputs, results, checkpoints, runtime
   packages and the execution lock file are retained. Other jobs are not selected.
4. Use Activity's Resume when appropriate, or create a new submission to adopt
   fixes from an updated app. Resume preserves the original job's worker code.

New workers save process IDs **and process start identities**, so cleanup rejects
reused PIDs and does not infer ownership from an open lock file or a process name.
It requests termination, then force-stops only verified leftovers that resist it.
If macOS will not terminate a process, the app explains that a restart is needed.
Older jobs without these identity records cannot always be cleaned automatically;
save work and restart the Mac when directed. Never delete `execution.lock` to
unblock a job.

**Copy support report** omits raw logs, sequences and file paths. **Copy visible
log** is a separate action; review that text for sensitive content before sharing.
No report is uploaded automatically.

Detailed log semantics: [Engine progress](ENGINE_PROGRESS.md).
Implementation and fixture coverage: [Lab Book 0189](../lab_book/0189-add-job-progress-viewer-and-recovery.md).

Changing tabs, workspaces or the displayed run does not stop a submitted job.
**New run** leaves it in the queue. Queued settings are saved independently;
later edits to the form apply to the next submission. Externally referenced
inputs are checked again before execution; changing those files can cause a
queued job to fail its provenance check. Do not edit a queued run's files.

## Scheduling and recovery

Only one managed job owns the shared execution lock at a time. Waiting jobs
start automatically after it releases that lock, including when it completes,
fails or finishes stopping. A Protein Hunter engine/scaffold batch retains the
lock until the whole batch ends. Existing resident-worker and cycle scheduling
remain within each job; queueing does not load competing models onto the GPU.

Waiting jobs are displayed by submission time. The existing lock scheduler does
**not guarantee first-in, first-out ordering** and has no priority or reorder
controls. The queue also includes compatible jobs submitted through the MCP
bridge. Very old RFdiffusion3 jobs launched before the durable broker retain
their legacy monitoring and cannot be detached using New run while active.

Closing Studio leaves submitted jobs running or waiting. Reopening Studio reads
the durable job registry; use the queue to choose which job to display. This
does not promise unattended recovery after a computer restart: use Activity's
Resume action for interrupted jobs. Saved jobs retain their frozen runtime.

While submission is still saving a job, its Start/New run controls briefly stay
disabled to prevent duplicate submissions. If submission or cancellation fails,
the app reports the error; it does not silently discard the job.

The implementation and fixture coverage are recorded in
[Lab Book 0129](../lab_book/0129-queue-all-studio-workflows.md).

## Submission retries and stopping

Retrying the same saved submission reuses completed preflight preparation and
its immutable plan. Concurrent identical requests serialize against that request,
not against the entire job registry. Different saved run folders remain separate
runs even when their scientific settings match. Initial preparation may still
need to preserve and verify large model assets; the native app waits for it and
does not automatically create another request every few minutes.

Stop follows observed workflow descendants across process-group changes. The
GPU lease remains held while they exit; resistant children are terminated after
the grace period. A child stuck in an operating-system operation can keep Stop
pending. Studio never treats an open lock file alone as authority to kill a process.

App updates preserve old jobs' frozen worker code. To use the corrected 0.2.4
submission/cancellation behavior, create a new submission. On a Mac already
blocked by an orphan from an older worker, save other work and restart macOS
before updating/retrying. Keep existing results; deleting the lock file can let
incompatible workers overlap and is not a recovery procedure.
