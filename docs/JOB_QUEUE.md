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
