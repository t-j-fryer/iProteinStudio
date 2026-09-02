# Runtime consolidation v1: phase-one results

## Decision

Do not replace the shipped environments yet. The phase-one evidence supports two
promotion candidates:

1. repeat Boltz with the final stable PyTorch 2.14 wheel, then test the same lock
   on M1 Pro before changing the production pin;
2. reduce the nine logical runtime boundaries to eight by sharing one ordinary
   Protenix dependency environment between v2, Mini and Constraint while keeping
   the ordinary and Constraint source overlays explicit and separate.

The second change still needs full v2, Mini and Constraint regression, installer
update/rollback/removal tests and a fresh-install acceptance test. Every other
boundary remains separate until equivalent execution evidence exists.

## Dependency inventory

The shipped locks contain eight explicitly managed environments plus
RFdiffusion3's Foundry environment. They span Python 3.10--3.12, PyTorch
2.2.0--2.13.0 and NumPy 1.23.5--2.4.6. Matching only the PyTorch pin is not a
valid merge criterion.

Already consolidated within one boundary:

- ProteinMPNN, SolubleMPNN, LigandMPNN and AbMPNN;
- IntelliFold v2 Flash and full v2;
- Protenix v2 and Mini.

The strongest additional candidate is ordinary Protenix plus Protenix
Constraint: 53 shared exact package pins and only three low-level pin differences
(`filelock`, `msgpack`, `setuptools`). Both source trees expose the same
top-level `protenix` module, so a merged environment must select the source tree
explicitly rather than install one over the other. The ordinary Protenix
environment is the correct shared base because it contains `fair-esm`; the
Constraint checkpoint does not use the trained ESM projection, but sharing that
single dependency is safe and avoids creating a second copy.

LASErMPNN plus the MPNN suite is not yet supported as a merge. Although both
currently use PyTorch 2.2.1, their locks have 11 exact-pin conflicts, including
NumPy 1.26.4 versus 1.23.5, and LASErMPNN owns compiled graph extensions. Boltz
and RFdiffusion3 likewise remain separate: RFdiffusion3's Foundry environment has
a substantially larger stack and a different NumPy generation. IntelliFold and
OpenFold remain separate despite sharing PyTorch 2.6.0 because their locks have
12 conflicts and NumPy 1.26.4 versus 2.4.6.

## Boltz 2.2.1 with PyTorch 2.14 final RC

Hardware: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1.

The disposable candidate began from the complete 69-package shipped Boltz lock.
Only PyTorch changed, from 2.13.0 to 2.14.0, and `uv pip check` passed. The exact
CPython 3.11 macOS arm64 wheel came from PyTorch's official test channel; its
SHA-256 was
`1040f689e560ba6e02a0a147dfb9ec8dfdd3e4486ebec4b24dc8fdaa258fa9ba`.

Three control and three candidate fresh processes used the same 71-residue
sequence, explicit MSA, seed, sample count, checkpoint and FP32 launcher:

| Measurement | PyTorch 2.13 control | PyTorch 2.14 candidate |
|---|---:|---:|
| Runs | 3 | 3 |
| Wall time, all runs | 16.925 +/- 0.308 s | 32.715 +/- 27.831 s |
| Warm wall time | 16.925 +/- 0.308 s | 16.650 +/- 0.791 s (n=2) |
| First candidate process | -- | 64.845 s |
| Model progress time | 4 s each | 5, 4, 4 s |
| SVD CPU-fallback lines | 1 per run | 0 per run |
| pTM | 0.8701755404 | 0.8701754808 |
| Complex pLDDT | 0.9070275426 | 0.9070275426 |
| CA RMSD to first control | approximately 0 A | 0.00001119 A |

All six structures passed geometry validation. Each version was internally
deterministic by structure hash. The candidate's first process incurred about
48 s beyond its two warm processes even though model progress differed by only
one second. The cause is unresolved, so the cold-start penalty is retained in
the record rather than averaged away. PyTorch 2.14 eliminated the one counted
`linalg_svd` CPU fallback on this input and preserved numerical output to far
below any structurally meaningful difference.

This is strong M4 evidence, not a production promotion. Repeat with the stable
channel wheel after release and run the controlled M1 Pro acceptance matrix,
including cold start, repeated predictions, multimer/ligand inputs and resident
campaign execution.

## Protenix shared dependency environment

One controlled Protenix Constraint job was run both through its dedicated
Python 3.12 environment and through the ordinary Protenix Python 3.11 dependency
environment with the Constraint source selected by `PYTHONPATH`. Both used
PyTorch 2.7.1, native MPS with fallback disabled, strict checkpoint loading,
10 recycles, 200 diffusion steps, seed 42 and explicit MSAs.

| Measurement | Dedicated Constraint | Shared Protenix dependencies |
|---|---:|---:|
| Wall time | 64.065 s | 60.999 s |
| Model forward time | 33.73 s | 34.38 s |
| pLDDT | 79.486488 | 79.486481 |
| iPTM | 0.23405743 | 0.23405761 |
| Ranking score | 0.27704433 | 0.27704448 |
| CA RMSD | reference | 0.00004417 A |

Both outputs passed geometry and exact-cardinality checks; neither reported CPU
fallback. This validates the source-overlay architecture for one job. It does
not yet validate the installer migration or every Protenix model.

## Storage and safety

The current ordinary and Constraint Protenix environments each occupy about
1.0 GB logically. A shared dependency environment should therefore remove about
one environment's logical duplication, while the existing APFS clone-backed
installer means physical savings may be smaller. The Boltz candidate environment
(1.2 GB) and download cache (1.6 GB) remain only under ignored Validation paths.
No package, model, source tree or receipt under `~/.iproteinstudio` was changed.
