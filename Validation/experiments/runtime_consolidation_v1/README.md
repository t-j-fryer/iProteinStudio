# Runtime consolidation v1

This experiment asks which iProteinStudio engine environments can be simplified
without changing an installed runtime or weakening scientific validation.

## Safety boundary

- Experiment environments and generated results live only under the ignored
  `Validation/output/runtime_consolidation_v1/` tree.
- The production `~/.iproteinstudio` environment is read-only. Its Boltz
  checkpoint and chemical-component data may be reused by path, but no package
  is installed, removed or upgraded there.
- Every candidate environment is created from an explicit Python interpreter
  and records its package inventory before prediction.
- CPU prediction and silent MPS fallback are forbidden. The known Boltz SVD
  fallback is counted if it occurs.
- Existing output is never overwritten.

## Dependency inventory

```bash
python3 Validation/experiments/runtime_consolidation_v1/audit_locks.py
```

This reads the shipped hash locks and writes a machine-readable comparison under
`Validation/output/runtime_consolidation_v1/dependency_audit/`. Matching a
PyTorch version is not treated as proof that two engines can share an
environment; all direct and transitive version conflicts remain visible.

## Boltz 2.14 candidate

PyTorch 2.14 is staged on PyTorch's official test wheel index before its stable
release. The command below installs the current Boltz lock in a disposable venv,
replaces only `torch` from an exact macOS arm64 wheel URL with its SHA-256 in the
URL fragment, verifies the environment, exercises the upstream MPS allocator
reproducer and interleaves three current-runtime controls with three candidate
predictions.

```bash
caffeinate -dimsu python3 \
  Validation/experiments/runtime_consolidation_v1/run_boltz214.py \
  --input-yaml /path/to/input.yaml \
  --msa /path/to/query.a3m
```

Results from the staged test wheel cannot by themselves justify a shipped pin.
The experiment must be repeated against the final stable wheel before promotion.
The measured phase-one result and promotion gates are in [RESULTS.md](RESULTS.md).

## Protenix shared-dependency candidate

Protenix v2 and Protenix Constraint use the same upstream commit and PyTorch
version, but require different patched source trees under the same Python module
name. This test keeps those source overlays separate while running both through
one dependency environment:

```bash
caffeinate -dimsu python3 \
  Validation/experiments/runtime_consolidation_v1/run_protenix_shared.py \
  --input-json /path/to/one_constraint_job.json \
  --target-msa /path/to/target.a3m
```

The production environments remain read-only. A successful single-job result is
only an architecture feasibility gate; full v2, Mini and Constraint regression,
installer rollback and removal tests remain necessary before consolidation.
