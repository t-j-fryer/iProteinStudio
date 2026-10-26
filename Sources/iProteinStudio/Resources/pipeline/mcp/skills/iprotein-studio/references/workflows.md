# Route by scientific task

Pass the exact enum below to `workflow_guide`; inspect the connected planner's
schema for required fields. Tool names here omit client prefixes.

| Task | Guide enum | Planner |
| --- | --- | --- |
| Fold complete sequences | `prediction` | `prediction_plan` |
| Prepare a target structure/MSA | `prediction` | `target_prepare_plan` |
| X-token Hallucination / Protein Hunter | `iterative_design` | `iterative_design_plan` |
| RFdiffusion4 | `rfd4` | `rfd4_plan` |
| Template-guided Boltz motif beta | `motif_beta` | `motif_beta_plan` |
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

ESMFold2 Fast requires complete sequences. Full also supports fixed-framework
CDR-only X-token starts with masked scaffold alignment columns. Whole-chain
Full X-token hallucination remains unsupported. Use complete sequences for
ordinary prediction/checking or refinement after a separate initialization stage. They do not apply target templates, pocket guidance or Boltz's
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

## RFdiffusion4 and recommended workflows

RFD4 supports monomers, protein/ligand binders, supported nanobody frameworks,
structural motifs, partial diffusion, inverse folding and native annotated inputs.
Fixed/iterative/greedy/beam sequence exploration and native RFD4 rollout search
are separate choices. Read the schema and evidence reference before setting budgets.
Recommended protein/nanobody sequence targets use target_prepare_plan with Full
and automatic per-chain MSAs first; preserve colon-separated B/C/... chains,
explicit hotspot numbering and target preparation provenance. Bare hotspot
numbers are ambiguous for multiple chains. The design-time budget begins after
preparation; queue time is excluded.

Monomers may use RFD4, native unconditional RFD3 followed by refinement, or a
compatible X-token predictor. Exclude RFD3 fixed-framework nanobody generation:
the user's trial failed and this route is not pursued. RFD4 optimization offers
partial diffusion and inverse folding, not unrelated generation tasks.

## Template-guided Boltz motif beta

Discover motif_beta_catalog, then workflow_guide(motif_beta). The public planner
and pipeline_recipe_plan route motif_beta use the same adapter as the app's
Design → Motif scaffolding → Atomic motif beta button. Stage prepare writes
files only; backbones and cycles perform compute through job_start. Requests are
bounded to 1–5 roots. Inspect the returned total prediction budget: guidance adds
separate untemplated ranking checks, and multiple designers/policies add arms.
Original-input atom mappings and ligand identities are immutable. Template
geometry can come from mapped RFD3 residues or the original benchmark residues.
Only Boltz automatic cycling is exposed; Protenix/IntelliFold features are
CPU-qualified, not qualified model workflows. General custom-motif X-token
scaffolding is unavailable. See references/evidence.md for the evidence limits.
