# NISE stage-directory continuation

This validates a user-selected submission policy for the paused biotin campaign.
It is not a speed benchmark or a production-default promotion. Read `manifest.json`
and Validation Lab Book 0032 for the declared budget, controls and results.

From the repository root, with the managed installation in `NANOHUNTER_ROOT`:

```sh
python3 Validation/experiments/nise_stage_batch_resume_v1/prepare.py \
  --source-job job-002ee4e5c61e --mode smoke \
  --records Validation/output/nise_stage_batch_resume_v1/smoke
```

The helper prepares a frozen two-input validation plan; it does not launch it.
Submit the returned plan ID and SHA256 through MCP `job_start`. The smoke interrupts
one structure directory request after a native writer marker, before controller
commit, then recovers completed work and finishes the missing input. It sends both
structures to one affinity request and verifies a repeated resume adds no inference.

After successful validation, use `--mode continue` with a separate records directory.
This verifies original scientific source files and all completed cycle00 receipts,
keeps the original config and snapshot, and creates a separately fingerprinted
continuation snapshot and plan pointing to the same output. Start that plan via
`job_start`; resuming the old plan would retain singleton submission.

The new worker saves per-input checkpoints while the full pending stage runs.
Selective affinity retains its original selection batch size and stopping rule.
The request stream and preprocessing order can change future unfinished predictions;
completed predictions are reused unchanged. Mixed per-input seed overrides are
unsupported in this opt-in route. No early exposure stopping is enabled.
