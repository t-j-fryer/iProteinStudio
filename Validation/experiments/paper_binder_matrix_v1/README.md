# Shared-target optimization and paper binder predictions

This isolated experiment tests optimizations on five **different** binders
against SUMO96, then predicts the 674 unique binder–target sequence pairs in the
user-supplied paper table. No installed package, app default or model weight is
modified. All GPU work uses immutable Studio plans and the shared execution lock.

## Scientific settings

Binder chain A is explicitly query-only. Target chain B uses a frozen supplied
alignment capped at 128 records. SUMO uses the established 96-aa sequence and its
matching alignment. AF3 prediction data JSONs supplied the other target alignments;
the ALFA and Myc peptide-tag alignments contain duplicate query records only.
These are marked query-only and are not represented as having homolog support.

| Engine | Recycles/loops | Requested diffusion steps | Target MSA |
|---|---:|---:|---|
| Boltz2 | 3 | 25 | up to128 |
| IntelliFold Flash | 10 | 25 | up to128 |
| OpenFold3 | 3 | 25 | up to128 |
| Protenix v2 | 10 | 25 | up to128 |
| Protenix Mini | 4 | 1 | up to128 |
| Protenix Constraint | 10 | 25 | up to128 |
| ESMFold2 Full | 20 | 13 | up to128 |
| ESMFold2 Fast | 3 | 50 | none |

Exact token sizing; one sample. Boltz potentials remain off, matching the earlier
benchmark. No templates or restraints are supplied. Native ESM diffusion schedules
truncate internally: requested13/50 means10/34 denoising iterations respectively.
IntelliFold Full is excluded as requested.

The main/designed binder sequence is used. The source table's 33 differing assayed
sequences are retained as metadata, not substituted. One Myc-labelled row contains
a TrxA sequence; that sequence is retained and the inconsistent label is flagged.

## Protocol and outputs

`inventory.py` freezes the source table and validated MSAs. `prepare.py PHASE`
freezes scripts/configuration and creates a broker preflight. Review its command,
runtime bindings and digest, then use the managed `studioctl start` command.
Never run the GPU worker directly.

Each optimization arm receives one warmup, five different SUMO binders with paired
seeds42–46, and one separately labelled cProfile replay. The numerical gate is
declared in the plan. `analyse.py PHASE` independently audits hashes, confidence
and structures, then writes paired comparisons and timing figures. Named stages
are nested and must not be added together. Different sequence lengths make a
difference of medians distinct from the median of paired differences.

Follow-up phases test OpenFold direct coordinate arrays, positional-offset-aware
ESM target embeddings, reversed-order Boltz residency, and upstream Protenix
invariant diffusion/duplicate-template computation. Failed and superseded attempts
are retained, including harness failures documented in the Lab Books.
One additional, explicitly labelled one-pair probe tests Protenix trunk-only BF16;
it can proceed to five-pair confirmation only if both faster and within the gate.
It cannot qualify a change on its own. `summarize.py` combines the audited screens
without pooling unmatched session controls.
The additional `esm_memory` phase checks a 4 GiB free-buffer cache limit after
observing increasing native GPU allocations across input lengths. Its preceding
native controls are reused for numerical equality only, not for a causal speed
claim. Active model weights, precision, recycles and diffusion are unchanged.

After reviewing those results, `prepare_campaign.py SELECTION.json` creates the
full immutable plan. Selection must explicitly list all eight engine variants and
seeds; one seed42 per design is the current assumption. Each engine first completes
one audited prediction using the longest binder for each of seven distinct
targets before processing the remaining designs. Every unit records
sequence/finite-output checks and hashes.
Interrupted units are preserved and retried in separate directories; completed
units are reused only after verifying their hashes.
The coordinator permits one retry after a failed engine worker, retaining both
logs and all partial units. It forwards live unit progress to Studio. External
model weights and selected data assets are SHA-256 fingerprinted during preflight
and verified before each resident starts; weights are never copied into this
experiment. Asset verification, cold initialization and per-process cleanup are
recorded separately under `sessions/<pid>/`. `python3 test_control.py` exercises
recovery and tamper rejection without running a model.

`campaign_report.py` joins predictions to all original table columns and writes
native scores, ipSAE(min) where PAE exists, SUMO crystal-core RMSD, and detailed
stage timings. OpenFold's PDE is not converted into a fabricated PAE/ipSAE score.
SUMO core RMSD evaluates only the target fold, not binder affinity or docking pose.

Generated results: `Validation/output/paper_binder_matrix_v1/`.
Project Lab Book: `lab_book/0230-shared-target-paper-predictions.md`.
Validation Lab Book: `Validation/lab_book/0062-shared-target-paper-predictions.md`.
