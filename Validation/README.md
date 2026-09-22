# Validation

This tree records reproducible scientific, runtime and performance experiments.
Read [AGENTS.md](AGENTS.md) before modifying an experiment. Use the
[Validation Lab Book](LAB_BOOK.md) for the dated index and the
[project Lab Book](../LAB_BOOK.md) for promotion decisions.

| Location | Contents |
| --- | --- |
| `experiments/` | Declared manifests, executable harnesses and compact qualification records |
| `lab_book/` | Hardware, settings, measurements, failures and untested conditions |
| `output/`, `cache/` | Ignored local raw outputs and caches; links there describe reproducible local artifacts, not files included in a GitHub clone |

## Recent qualification

- [Portable runtimes](lab_book/0047-portable-runtime-qualification.md): package
  relocation, scientific equivalence, installation and preservation contracts.
- [GPU scratch recovery](lab_book/0048-mps-scratch-recovery.md): the local
  filesystem incident, reversible repair and repeated Boltz/PSICHIC checks.
- [Apple runtime profiles](lab_book/0041-crystal-msa-runtime.md): paired runtime
  comparisons with stated structure/MSA policies and limits.
- [Resident inference](../docs/RESIDENT_INFERENCE.md): terminology, measured
  scheduling decisions and the original qualification boundaries.

Earlier experiment folders are retained as immutable methodology/evidence.
Their README files describe the campaign at that time; they are not the current
installer or app defaults. Use the [current documentation](../docs/README.md)
for those. No neural inference starts merely by opening or reading this tree.

A performance experiment keeps sequences, seeds, sample counts, diffusion steps,
recycles and alignment inputs fixed. Every promoted setting needs an audited
output comparison and lifecycle/memory checks, not just a faster elapsed time.
New model runs go through Studio's immutable preflight/job broker and shared
execution lease. Fresh-Mac and cross-chip acceptance must be recorded explicitly.
