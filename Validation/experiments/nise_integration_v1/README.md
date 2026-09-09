# NISE integration acceptance

This is the bounded lifecycle test described in `protocol.json`. Its runner
creates the exact source/weight-fingerprinted manifest and immutable broker plan
before any inference. The broker holds Studio's shared execution lease. Completed
raw attempts stay under ignored `Validation/output/nise_integration_v1/`.

```bash
python3 Validation/experiments/nise_integration_v1/campaign.py plan \
  --output Validation/output/nise_integration_v1/NEW_ATTEMPT \
  --source /path/to/original/nise_fluorescein
python3 Sources/iProteinStudio/Resources/pipeline/mcp/studioctl.py start PLAN_ID PLAN_SHA256
```

The plan command uses `NANOHUNTER_ROOT` for the installed engines and normal
Studio job registry. Do not invoke `run` directly for GPU work. A successful
attempt produces `audit.json`; the broker job must also finish successfully.

The original smoke deliberately apo-tests the sampled child regardless of the
search filter, so it is an execution fixture rather than a selected hit. Its
actual measured child passed both consistency thresholds; see entry 0013.
It does not constitute a broad-search or efficacy test. Synthetic full-search
and interruption coverage is in `Tests/test_nise_science.py`.

See [Validation Lab Book 0013](../../lab_book/0013-nise-integration-acceptance.md).
