# Exact-pose spatial review

In Results → Hits (or Predict results → Filter & export), expand **Epitope,
ligand contacts & burial** and enable spatial criteria. Score rules and the
spatial criteria are combined before sorting and family limits. Select Custom
filters to review designs beyond the original saved verdicts.

Choose protein residues or small-molecule atoms. **Inspect exact pose IDs** lists
author chain/residue IDs, insertion codes and ligand atom names from the first
assessed candidate. Enter the protein chains used for contacts and the target
chain. Use explicit target residue IDs such as `40,99,107A`; ranges and numbering
from a different PDB are not substituted. In ligand mode, select one ligand
residue and exact predicted atom names; blank atom names means all ligand heavy
atoms. A ligand may share the protein's author chain when its nonpolymer residue
is explicitly selected.

The distance for each selected target residue or ligand atom is its shortest
distance to any selected protein heavy atom. **Every selected site** compares
the maximum of those nearest distances with the cutoff; **Any selected site**
compares the minimum. The boundary is inclusive. Missing sites, multiple
coordinate models, duplicate chains, alternate locations, unoccupied atoms and
nonfinite coordinates fail rather than receiving guessed values. These are
computational pose criteria, not experimental binding measurements.

Ligand analysis also reports **100 × (1 − bound/isolated ligand SASA)**, with
optional minimum/maximum burial filters. It reuses the existing RDKit FreeSASA
Shrake–Rupley protocol: heavy atoms, RDKit VdW radii,1.4Å probe and the same ligand
conformation. Bound area includes all nonwater atoms in the full complex, not
only the protein chains chosen for contacts. It is a solvent-accessibility
measure, distinct from the solvent-excluded surface drawn in ChimeraX.

**Require recorded geometry pass** checks an existing, integrity-checked receipt
for the exact pose, including its original linker-exit/atom-condition policy.
Missing or corrupt matching receipts cannot pass that requirement. Leaving the
requirement off allows distance/SASA review independently; corrupt receipts are
reported as warnings. The review does not rerun a linker classifier or infer a
chemical graph from names. No input-SMILES atom indices are remapped.

Click **Analyze N candidates** explicitly. This is CPU-only and uses the detected
Boltz-2 environment's Gemmi/RDKit/SciPy dependencies; Setup must provide that
environment, but no predictor is run. Missing dependencies are named in the
error. Changing criteria requires Analyze again; unchanged physical measurements
are reused across cutoff, coverage, burial and recorded-verdict changes.

Completed units are stored outside scientific run outputs under Studio's
`analysis/results-spatial/v1` support directory, keyed by coordinate SHA256,
selection and implementation. Separate assessment receipts record full policy,
versions and geometry-receipt identity. Per-unit file locks prevent duplicate
writers. Cancel or leave the Hits tab to stop; completed units resume from cache.
The row updates are batched so a large analysis does not rebuild the UI per unit.

A bounded preview includes passing and failing measurements, even if no hits
currently match. New matches, per-site distances, SASA values and receipt links
appear in Hits.
The new metrics can be sorted/filtered like other recorded metrics and are
included in CSV, with source pose, pose SHA256, policy SHA256 and receipt path.
Changed pose metadata, source assessment or criteria invalidate old matches.
Original scores, hit verdicts, structures and job snapshots are not rewritten.

# ChimeraX manuscript style

**External viewer** defaults to the manuscript script when the chosen application
is ChimeraX. Other viewer applications receive the coordinate file. Choose
**Save manuscript-style ChimeraX script** for a standalone local Python script,
or **Open coordinates without styling** for plain opening.

The presets reuse manuscript settings: white background, orthographic camera,
soft lighting; grey40%-transparent target surfaces and teal emphasized protein
cartoons for complexes; grey60%-transparent protein surfaces and gold ligand
sticks/55%-transparent ligand surfaces for pockets. The camera fits each new
structure with a margin. It does not reproduce a paper panel's hand-selected
camera/cutaway or classify visual accessibility.

In **Manuscript style settings**, optionally name emphasized protein chains for this structure.
Those IDs must exist in the opened structure. Explicit RFD4 design-chain roles recorded in the run are used by default.
No binder/target identity is inferred from a chain letter. Without explicit roles, multichain protein models
remain neutral; a monomer receives a coloured cartoon. Ligands are selected from
ChimeraX's structure classification. Commands target newly opened model IDs,
preserve other models and never change coordinates. The script verifies the
source file hash before and after opening.

The same menu is available in design results, prediction results, the Predict
progress pane's **Open a prediction** menu and reusable prediction-library rows.
The progress menu lists25 models; View Results provides all models and pages.

## CLI/MCP spatial and style review

Use `candidates_list` after `results_overview`, retain its snapshot digest and
choose exact candidate IDs and coordinate artifact index. `results_spatial_plan`
accepts1–100 IDs, that snapshot and the versioned spatial policy. Policy fields
use author chain/residue IDs and exact predicted atom names as described above;
threshold fields are strings, matching the native form. The returned immutable
plan freezes pose hashes, policy, implementation and the analysis runtime.
Review it and use `job_start`; the existing shared queue, keep-awake, cancellation,
retained-code/runtime and per-unit resume contract apply. No predictor is run.
Completed/error rows and cache receipts live outside the original run. Supply
its completed `spatial_job_id` to `results_review` or `results_review_export`;
only explicitly selected passing poses match. Failed/missing or unselected
poses cannot pass. A changed run snapshot or receipt is rejected.

`viewer_script_export` accepts one candidate, snapshot digest, coordinate
artifact index and optional `emphasized_chains`. It exports a ZIP containing
`manuscript_style.py`, its exact sibling structure and source metadata. Extract
these together, then open the Python script in ChimeraX. It verifies coordinate
identity and uses the same tested style recipe as the native app. MCP never
launches a viewer or infers an unrecorded binder chain. `export_read` retrieves
both viewer and scored-CSV archives for remote clients.
