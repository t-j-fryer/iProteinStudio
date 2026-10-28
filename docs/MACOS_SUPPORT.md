# macOS requirements: packages versus models

Audited 2026-10-28. Studio itself requires macOS 14 and Apple silicon. No
shipped component is declared to require whatever the newest macOS release is;
requirements are specific minimum versions.

| Component | Current Studio minimum | Evidence and cause |
| --- | --- | --- |
| ESMFold2 Full, Fast and Fast-600M; RFdiffusion3; OpenFold3 | 26.2 | The shipped MLX core and libraries contain Mach-O `minos 26.2`. These exact binaries have a real deployment requirement. |
| Protenix v2 and Mini | 26.0 | The highest requirement in the package comes from `python/bin/kalign`, built with `minos 26.0`. This is an auxiliary executable's build requirement, not an established requirement of the Protenix model. |
| RFD4 | 26.2 support gate | Its runtime manifest and audited native binaries require no more than 14.0. The 26.2 catalog/UI restriction is conservative; this audit does not establish a need for it. Older-system inference is not yet qualified. |
| Boltz-2 and affinity; IntelliFold; Protenix Constraint; ProteinMPNN/SolubleMPNN/LigandMPNN/AbMPNN; AntiFold; LASErMPNN; NESSO; PSICHIC | 14.0 in Studio | These runtime catalog entries declare 14.0 or lower; the desktop app supplies the overall 14.0 minimum. Protenix Constraint uses a separate runtime from v2/Mini. |

Workflows inherit the highest requirement of their chosen engines. For example,
RFD4 followed by ESMFold2 Full still needs the shipped 26.2 MLX runtime, even if
RFD4's standalone restriction is later relaxed. NISE and Protein Hunter likewise
depend on the selected predictors and sequence designers rather than adding a
universal latest-macOS requirement.

These are **package/support requirements**, not intrinsic properties of protein
models. [MLX's general installation documentation](https://ml-explore.github.io/mlx/build/html/install.html)
lists macOS 14+, while its macOS-26 wheel can contain 26.2-targeted binaries
([upstream issue](https://github.com/ml-explore/mlx/issues/4525)). Wheel filenames
alone do not reliably express the minor-version requirement. Apple also lists
macOS 14+ for its documented [PyTorch MPS configuration](https://developer.apple.com/metal/pytorch/).
Those general statements do not override the exact libraries Studio ships.

## What would be needed for broader support?

- For the MLX engines, package an appropriate lower-targeted MLX build and
  qualify the actual operators, numerical results and performance on older macOS.
- For Protenix v2/Mini, replace or rebuild the bundled Kalign for an older target
  and qualify the alignment and prediction paths. Do not silently substitute it.
- For RFD4, first run the existing immutable package on older macOS and check the
  required MPS operations and end-to-end results before lowering the support gate.

No OS gate, scientific default or runtime archive was changed by this audit.
Binary deployment metadata is necessary evidence; it does not prove successful
inference on an untested OS. The audit and reproducible counts are recorded in
[Lab Book 0619](../lab_book/0619-rfd4-label-and-macos-audit.md).
