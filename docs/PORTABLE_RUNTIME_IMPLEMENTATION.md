# Portable runtime distribution and experimental PSICHIC

Runtime release profile: `runtimes-2026.09.20-1`. App and MCP versions advance independently; `VERSION`, `BUILD_NUMBER` and the bundled `MCP_VERSION` are authoritative. See [Lab Book 0177](../lab_book/0177-integrate-psichic-portable-runtimes.md) and [qualification record](../Validation/experiments/portable_runtimes_v1/release_qualification.json).

PSICHIC is an optional **experimental** alternative wherever the NESSO ligand screen is offered: NISE initial/refinement and optimisation screening, and ligand Protein Hunter/RFdiffusion3 shortlist verification. Existing settings continue to select NESSO. PSICHIC ranks **1 − predicted_nonbinder**, reports affinity and three class probabilities, and has no ligand-placement-confidence term. Boltz retains NISE structural checks and its final objective. PSICHIC uses MPS ESM batches of eight, CPU graph batches of sixteen and four CPU threads. Complete sequences up to 700 residues are supported.

## Installation and updates

The app downloads optional standalone-CPython engine archives from GitHub Releases. Its shipped catalog pins each archive and file inventory by SHA-256; downloaded metadata cannot authorize new executable code. Each runtime contains its exact engine/dependency closure and relocatable native libraries. Installation verifies the platform, archive, inventory and actual imports before activating a version. Ordinary users need no Xcode, Command Line Tools, Git or package compilation for these profiles. The source-builder route remains an explicit developer opt-in, `IPROTEINSTUDIO_BUILD_FROM_SOURCE=1`; there is no silent source-build fallback.

The 12 archives total approximately 2.94 GB compressed, downloaded only for selected components. They exclude learned model weights. Model assets download separately from approved upstream URLs with pinned checksums. LASErMPNN's required fixed chemical geometry tables and dataset identifiers are included as static data; they are not its learned checkpoint. The app archive does not embed these engine runtimes or weights.

The native app requires macOS 14 or later. These Protenix v2/Mini profiles require macOS 26.0 or later; OpenFold3 and RFdiffusion3 require 26.2 or later. These are minimums: 26.6.1 qualifies. Setup disables incompatible optional selections, and the installer checks compatibility before downloading. Lower-OS engine profiles require separate rebuilding and qualification.

## Recovery and reproducibility

Activation uses a durable journal covering version, legacy aliases and receipts. Interrupted switches recover; earlier versions and model assets remain available for rollback. Failed downloads retain resumable partial files and cannot activate an unchecked archive. Component failures are reported separately, allowing successful components to remain usable.

At preflight, managed jobs retain exact portable runtime identities, adapter/bridge code and independent model-data copies. APFS clones avoid duplicating physical blocks where supported. Queued and resumed jobs use these retained paths even if the installed runtime or adapter changes. Saved scientific requests remain unchanged; derived runtime-bound configurations record their original and derived hashes. Workers verify inventories and reject tampering. Legacy environments are outside the portable preservation guarantee until migrated.

The shared registry declares capabilities, scheduling, runtime mappings, aliases, model paths and adapter identities. Shared adapters preserve upstream settings and the previously measured NESSO cache, Flash padding and Boltz/IntelliFold Torch 2.14 profile choices. This release does not change diffusion steps, model sizes, recycles or scientific guidance to claim a speedup.

## Qualification and limits

All 14 paired scientific relocation checks passed on the current M4 Max/macOS 26.6.1: Boltz 2, IntelliFold Flash/full, Protenix v2/Constraint, OpenFold3, RFdiffusion3, AntiFold, NESSO, ProteinMPNN, SolubleMPNN, LigandMPNN, AbMPNN and LASErMPNN. PSICHIC separately passed 64 CPU-reference cases through its production GPU/CPU adapter with maximum absolute output difference below 0.001. Final archive changes to Python metadata/Finder metadata are recorded separately from scientific code; repaired LASErMPNN data was retested with actual inference. Test launch failures and their corrected reruns remain in the Lab Book.

Fresh-Mac/no-developer-tools acceptance testing is explicitly deferred. This Mac's successful relocation/installation tests do not substitute for that test or establish support on every Apple chip. No new biological-binding result or controlled throughput improvement is claimed. Distribution remains the existing ad-hoc-signed trusted beta with Sparkle EdDSA-signed updates, not Developer ID signing or Apple notarization.

## Extending the system

Add a registry descriptor and validated adapter; freeze its code, dependencies and model contracts; qualify relocation and scientific outputs; publish a new immutable runtime identity; then update the app's trusted catalog. Never overwrite an archive or delete a version retained by a job. New model or hardware-specific acceleration profiles receive distinct identities. Exposing a new capability still requires explicit native UI and versioned request-schema changes.

## Optional GPU troubleshooting

Normal job startup does not inspect or modify Apple's shared temporary GPU
folder. A bounded diagnostic remains available only when explicitly invoked for
support, using the managed control Python:

```bash
ROOT="$HOME/.iproteinstudio"
"$ROOT/components/control/current/python/bin/python3" -B \
  "$ROOT/mcp/iprotein_mcp/gpu_storage.py" --diagnose
```

It tests only creation/removal of its own empty probe folder and reports JSON;
it never enumerates or clears shared contents. The one-time repair in
[Lab Book 0178](../lab_book/0178-repair-mps-scratch-stall.md) preserved the affected
directory with user authorization. That incident does not justify a filesystem
check before every scientific job. Removal of that automatic check is recorded
in [Lab Book 0179](../lab_book/0179-simplify-startup-and-refresh-distribution-docs.md).
