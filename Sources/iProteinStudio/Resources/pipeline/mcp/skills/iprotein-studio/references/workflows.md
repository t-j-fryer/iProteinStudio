# Route by scientific task

Pass the exact enum below to `workflow_guide`; inspect the connected planner's
schema for required fields. Tool names here omit client prefixes.

| Task | Guide enum | Planner |
| --- | --- | --- |
| Fold complete sequences | `prediction` | `prediction_plan` |
| Prepare a target structure/MSA | `prediction` | `target_prepare_plan` |
| Protein Hunter | `iterative_design` | `iterative_design_plan` |
| Ligand NISE | `nise` | `nise_plan` |
| De novo RFdiffusion3 | `rfd3_protein_binder` | `rfd3_denovo_plan` |
| Partial diffusion | `rfd3_partial_diffusion` | `rfd3_partial_diffusion_plan` |
| Motif scaffolding | `rfd3_motif_scaffolding` | `rfd3_motif_scaffolding_plan` |

## Protein Hunter

Use SolubleMPNN by default for soluble protein de-novo binders. Antibody
frameworks require their supported sequence-design route. LASErMPNN/LigandMPNN
are for small-molecule interfaces. Use `iterative_design_plan` for one engine or `iterative_batch_plan` for explicit
engine/scaffold allocations. Separate initialization and refinement use the
same validated planner arguments. Optional ligand screening is exposed through
`ligand_verification`; RFdiffusion3 uses `request.nesso`.

ESMFold2 Fast/Full require complete sequences: use them for prediction/checking
or refinement after a supported separate initialization stage, not X-token
hallucination. They do not apply target templates, pocket guidance or Boltz's
affinity head. RFdiffusion3 starts are for de-novo binders, not fixed-framework
nanobodies. Guidance is stage-specific.

The supported secondary-structure control is initialization-only
`--negative-helix-constant` in [0,1]; 0 disables it. It is not a guaranteed output
composition, and later cycles use normal MPNN sampling. Retired beta/mixed,
sustained-bias, loop-kill and inspection controls must not be recreated.

## RFdiffusion3

For protein de-novo design, omit `contig` so Studio derives binder-first grammar.
With no known epitope use `surface_scan`, not the target centre of mass.
`surface_patch` sets broad placement; `targeted_epitope` applies reviewed
hotspots; `manual` is expert XYZ placement. Predict every requested candidate
before ranking; do not prefilter by the generator's internal score.

Partial diffusion uses `partial_t` in Angstroms, not a percentage. Motif
scaffolding needs explicit non-empty residue atom selections. Do not translate
RFdiffusion1 syntax by memory. DNA/RNA design is out of scope in Studio.

## Ligand NISE

NISE here is small-molecule design; protein/cross-reactive NISE remains upstream.
Choose supported Protein Hunter or RFdiffusion3 starts, then the integrated
sequence/structure search. Obtain the current ligand atom map/signature before
setting atom requirements; SMILES/chemical-state changes can invalidate names.

Distinguish Boltz's default structure/affinity objective from optional NESSO or
PSICHIC prefiltering and from using those scorers as the optimisation objective.
Their outputs are not interchangeable. ESMFold2 structure generation is an
experimental unrestrained route with a supported screening objective; check the
guide/schema for compatible settings. Preserve postfold geometry checks.
Legacy noising fields in saved schemas are not the current GUI's default route.

## Read-only review example

`projects_list` → `runs_list` with a returned project → `run_status` and
`results_overview` with a returned run ID → `results_query` with a returned
dataset name. Describe actual available results; a limited response does not
establish that all candidates or cycles have been inspected.
