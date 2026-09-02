# iProteinStudio release notes

## 0.2.0 — updater foundation

- Adds separate RFdiffusion3 de-novo, partial-diffusion and motif-scaffolding
  workflows, including bundled p53–MDM2 examples.
- Adds a live RFdiffusion3 results dashboard: accepted backbones and verification
  structures appear during the run with structure browsing, score histograms,
  summary statistics and saved hit-filter verdicts.
- Preserves exact source-motif → designed-residue correspondence through
  generation, MPNN and prediction, and scores recovery of every explicitly
  constrained motif atom after one global alignment.
- Fixes the MLX adapter dropping residue-specific motif side-chain atoms, and
  fails motif scoring when any requested atom is absent rather than scoring a
  misleading partial intersection.
- Fixes RFdiffusion3 score distributions appearing empty after a live campaign
  changes from backbone metrics to predictor metrics.
- Reuses one resident Boltz, IntelliFold or Protenix Mini model across every
  complex or binder-only RFdiffusion3 verification stage; full Protenix v2 uses
  its faster measured directory-wave policy instead of reloading per design.

- Adds cryptographically verified Sparkle updates for trusted betas and future
  Developer ID releases, with a visible **Check for Updates…** command.
- Adds update preferences for automatic checks and automatic app downloads.
- Keeps application updates separate from scientific engines and checkpoints.
- Adds a final, size-aware confirmation before any selected engine is installed.
- Preserves projects, results, alignments, environments and model weights when the app is updated.
- Fixes a clean-Mac launch crash caused by SwiftPM's generated resource accessor
  falling back to an absolute development-build path.
- Fixes fresh AntiFold installation by removing an unnecessary `wheel` entry
  whose newly introduced, unhashed dependency made the locked install abort.
- Fixes Protenix installation aborting after package installation because a
  shared-data path was expanded before its local variable was initialized.
- Corrects the published `filelock` hashes used by LASErMPNN's build bootstrap.
- Lets deliberately pip-free RFdiffusion3 environments write and verify their
  installation receipts after successful GPU/checkpoint validation.
- Shows ProteinMPNN, SolubleMPNN, LigandMPNN and AbMPNN explicitly as the
  automatically installed core sequence-design suite in Engines.
- Retries transient MSA-service failures in Predict and reports the actual
  provider/network cause plus a durable diagnostic log instead of the generic
  and often misleading “MSA server could not be reached” message.
- Isolates every ColabFold retry so a truncated or non-archive server response
  cannot be mistaken for a cached MSA download and poison all later attempts.
- Runs Boltz-2 in full FP32 on Apple GPUs and resets unused PyTorch MPS allocator
  blocks immediately before each prediction batch. This addresses a reported
  allocator-state-dependent silent-numerics defect in PyTorch 2.13 that can vary
  by Apple GPU and macOS build.
- Replaces IntelliFold v2/v2-flash's three failing Apple `GatherND` formulations
  (pair lookup, atom compaction and atom-count repeat) with equivalent
  order-preserving indexed lookups, retaining native MPS and forbidding a silent
  CPU fallback.
- Validates protein backbone geometry before any Boltz or IntelliFold output is
  accepted or marked resumable, with a useful failure instead of a corrupted
  structure in the library.
- Prevents Boltz from redownloading its 1.8 GB chemical-component archive when
  the verified extracted component library is already installed.
- Stores Protenix and IntelliFold detailed confidence arrays as lossless,
  SHA-256-verified gzip files after scoring and geometry checks.
- Keeps one canonical copy of structures and batch logs while galleries,
  selected results and per-trajectory views use durable relative references.
- Shares exact MSAs and independently resumable pipeline snapshots through a
  content-addressed APFS store, without changing or deleting older projects.
- Correctly reports that automatic Protenix v2/Mini prediction uses five
  diffusion samples while the other supported engines use one.
- Fixes successful IntelliFold predictions being rejected after inference when
  their canonical output followed upstream's `_inputs/predictions` directory
  layout; staged coordinate inputs remain excluded from geometry acceptance.

Trusted beta update archives are signed with the project's Sparkle EdDSA key,
but the beta application itself is not Developer ID signed or notarized by Apple.

This release does **not** download a model or checkpoint as part of the app
update. New scientific components remain explicit choices in **Engines**.
