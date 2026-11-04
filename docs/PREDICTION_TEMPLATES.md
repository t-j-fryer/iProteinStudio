# Structure templates in Predict

Predict can guide selected protein chains with a PDB, CIF or mmCIF structure,
using the same **Guide** mode as Protein Hunter. This works for monomers and
protein complexes, including complexes that also contain a ligand.

1. Enter your sequences and choose **Read & assign chains**.
2. Turn on **Use a structure template**, then choose your PDB/CIF file.
3. Tick the **query chains** you want to guide. For a monomer this is usually A.
   For a binder–target complex, select only the target chains if the binder should
   remain untemplated. These are the chain letters assigned by Predict, which
   can differ from the letters in your structure file.
4. Select compatible engines and start the prediction.

| Engine | User structure guidance |
| --- | --- |
| Boltz-2 | Guide mode |
| IntelliFold v2 Flash / full v2 | Guide mode, local template features |
| Protenix v2 | Guide mode, local template features |
| Protenix Mini / OpenFold-3 | Unavailable; turn off guidance or deselect these engines |

Prediction has one setup form: alignments, sampling, throughput and all engine
settings are available without an Advanced tab. Template controls appear only
when **Use a structure template** is on. Switching it off removes the template
from the submitted configuration while retaining the file and chain choices for
later use. Older saved guided setups remain enabled on upgrade. Turning it on
without an existing file blocks starting.

The built-in **T4 lysozyme** example replaces any previous template selection
with its bundled experimental **2LZM** PDB, selects query chain A, and leaves
guidance off. The original PDB and mmCIF also ship under `examples/t4_lysozyme`.
No T4 alignment is bundled: the selected policy reuses or prepares one. No
structure is implicitly used as guidance while the switch is off. **4TW1** is
a bacterial LukGH complex, not T4 lysozyme; previously saved imported templates
remain user choices rather than defaults.

Changing guidance does not require re-reading unchanged sequences; changing
sequences or their alignment policy does. Templates and alignments are separate.

## Choosing chains and structures

The same structure and query-chain selection apply to every fold in a batch.
Only protein chain IDs present in every fold are offered. Split batches when
individual jobs need different templates. Identical copies of a protein share
model features, so select all copies or none. Unselected proteins receive no
user template; ligand coordinates are not a selectable template target here.

Use a structure of the same protein or a close sequence match. IntelliFold and
Protenix retain Protein Hunter's minimum 70% sequence identity and 70% coverage
checks and fail if the structure cannot be mapped safely. Boltz uses its own
sequence matching after Studio normalizes the structure to mmCIF. Mapping
failures appear in the run log; Studio does not silently fold without the
requested template. Guide mode supplies structural evidence, not a guarantee
of fixed coordinates. Strong restraints remain unavailable.

A guided prediction is conditioned on the supplied structure. It should not
be interpreted as independent confirmation of that structure or binding pose.

## Reproducibility, recovery and throughput

The picker imports a workspace-owned copy. Starting a native run preserves a
second copy under that run's `templates/` directory. MCP preflight instead
imports a checksummed artifact. Both paths record the template, selected query
chains and adapter provenance before entering the shared job queue.

Predict prepares engine-specific inputs under `template_inputs/<engine>/`:
normalized mmCIF for Boltz, local A3M/mmCIF bundles and a batch manifest for
IntelliFold, and explicit selected-chain metadata for Protenix's existing
inline-mmCIF converter. IntelliFold uses these local files without requesting a
template database download. Protenix v2 uses its existing managed Kalign
installation. Resolved MSAs are preserved.

Completed preparation has a checksum receipt. Interrupted preparation is
archived and rebuilt; missing or changed completed artifacts stop the run.
Template or configuration changes require a new run. Removing guidance from a
previously guided run, or adding it to completed untemplated results, also
requires a new run. Completed prediction chunks remain resumable.

Existing shape grouping, directory batches and concurrency settings are
preserved. One loaded engine process can still handle multiple inputs in a
chunk. This change adds no new throughput benchmark or persistent-worker mode.

## CLI and MCP contract

Add this optional field to a Predict configuration, or to the `request` passed
to `prediction_plan`:

```json
"template": {
  "path": "/path/to/structure.pdb",
  "chains": ["A"],
  "mode": "guide"
}
```

`chains` must be nonempty, unique protein chain IDs present in every job.
Omit `template` for ordinary prediction. MCP still requires preflight and
`job_start`; its plan digest, provenance checks and execution lease apply.
See [CLI](CLI.md#predict-a-batch-of-sequences).

Software acceptance covers synthetic structure conversion, multi-input routing,
MSA preservation, checksummed replay, chain constraints and saved-project
migration. Fresh neural inference and comparative scientific accuracy for this
Predict integration have not yet been evaluated; see [Lab Book 0107](../lab_book/0107-predict-structure-templates.md).
