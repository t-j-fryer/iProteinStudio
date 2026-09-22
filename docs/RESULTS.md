# Browsing results

Results belong to the saved run. Open them from its run controls or History;
completed work remains available during execution and after a failure. The
browser refreshes while open, including after a run resumes. Computed confidence
and saved filter verdicts are distinct from experimental binding evidence.

| Workflow | Organisation | Useful comparisons |
| --- | --- | --- |
| Protein Hunter | Framework/engine campaign → independent trajectory → start and design cycles → complex/binder-alone checks | Filter the design stage separately from independent checks; use saved filter verdicts for hits. |
| RFdiffusion3 | Generated backbone → MPNN sequence derivative → predictor complex and binder-alone structures | Compare derivatives and predictor agreement; generated-backbone geometry, motif placement and sequence-verification scores retain separate labels. |
| Predict | Input job → engine and stochastic model sample | Compare like-for-like score sources; template-conditioned results are labelled rather than presented as independent template validation. |
| NISE | Phase 0 stages/lineages → Phase 1 cycles/trajectories → final apo/holo checks | Separate folding completion, geometry, scoring eligibility and next-cycle selection; inspect NESSO/PSICHIC screens separately from Boltz scoring. |

Protein Hunter, RFdiffusion3 and Predict share name search, stage and score-source
filters. Protein Hunter batches additionally filter framework and design engine.
Overview distributions follow the selection; choose one stage/source when
comparing scores. Missing scores remain absent rather than zero. Each cycle or
sequence derivative contributes one representative metric; filter a predictor
explicitly when several assessment engines are present. Predict contributes one
value per displayed model sample. Clear filters to recover the complete view.

Predict can open results while running. Completed `chunk_complete.json` receipts
expose successful engine chunks before the final `predictions.csv` is written;
uncommitted raw files do not count as successful output. Final task failures are
listed in Overview without hiding successful structures. Reveal Run opens the
saved outputs and logs. A failed running chunk may only appear in the final CSV;
the run controls retain the live log in the meantime.

Confidence files are associated with their native model sample. A task-level
representative score is not applied to every stochastic sample. Ligand pLDDT
has its own label and is not substituted for protein/complex pLDDT. Unambiguous
single-model Boltz outputs include the matching saved affinity file; shared
input-level affinity is not assigned arbitrarily to multiple different models.

RFdiffusion3's ranked manifest covers a shortlist. Ranking replaces the matching
provisional assessment but does not remove completed derivatives outside that
shortlist. Such models retain their provisional/unranked status and do not acquire
a hit verdict. Parent backbones remain available throughout.

See [NISE](NISE.md#viewing-progress-and-structures) for preparation-stage progress,
sequence-only screening and the interpretation of intentionally omitted affinity.
