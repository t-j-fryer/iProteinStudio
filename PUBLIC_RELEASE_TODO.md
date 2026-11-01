# Public release candidate to do

Local preparation for the upcoming paper release. Changes here are not published
automatically; publication and release packaging are separate steps.

- [ ] Inspect the results viewer: live updates, grouping, score labels, filtering,
  molecular display and completed/interrupted runs.
- [ ] Inspect file management: workspace organisation, saved outputs, locating
  files, moving/exporting work and safe cleanup.
- [x] Include and validate the general live-results update: queue/progress/activity
  entry points and RFD4 results available before campaign completion.

The existing 0.2.30 app remains the preserved baseline. This candidate excludes
experimental peptide workflow code and private beta installation controls.

- [x] Fix persistent design-field labels and explain Metal kernel checks.
- [x] Add catalogue framework/CDR selection, sequence target preparation, balanced
  length allocation/custom counts, family-grouped RFD4 predictor choices and saved
  protein hit filters (Lab Book 0679).
- [ ] Qualify the newly exposed predictor/framework combinations end to end on GPU
  before a public binary release; CPU input preparation is not inference validation.
- [ ] Preserve and assess ligand context throughout mixed protein–ligand target
  design. Current protein refinement rejects such inputs rather than dropping entities.

- [ ] Complete mixed protein–ligand target qualification before publishing0.2.31: code, CLI/MCP, exports and UI help integrated; native CPU audits and offline tests pass. Keep draft and installed apps held until queued GPU checks pass (Lab0684).
