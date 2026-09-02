# Boltz MPS allocator control

This experiment compares two otherwise identical Boltz-2 launchers in fresh
processes on one fixed short-protein prediction:

- control: build 8, FP32 plus geometry validation;
- candidate: build 9, the same launcher plus `torch.mps.empty_cache()` directly
  before each prediction batch.

The script copies the exact YAML and MSA into the ignored output tree, records
their checksums and both wrapper checksums before compute, alternates three runs
per arm, and requires one structure, one confidence file, MPS execution and a
geometry pass from every run. The known Boltz `linalg_svd` CPU fallback is
counted; any other fallback fails the audit.

```bash
caffeinate -dimsu "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" \
  Validation/experiments/boltz_mps_allocator_v1/run.py \
  --input-yaml INPUT.yaml --msa QUERY.a3m \
  --control-wrapper BUILD8/pipeline/scripts/boltz_mps.py \
  --candidate-wrapper BUILD9/pipeline/scripts/boltz_mps.py
```
