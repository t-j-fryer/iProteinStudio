# Evidence for workflow choices

Reviewed 2026-10-26. This is a curated decision aid, not a live leaderboard.
Read it when choosing a workflow or explaining a recommendation. Preserve explicit
user choices; inspect installed schemas and current completed results before
claiming that a method is available or best for a new target.

## What the evidence supports

| Evidence | Decision it informs | Limits |
| --- | --- | --- |
| Recommended easy/hard workflows, project Lab Book 0572 | Easy protein/nanobody: native RFD4 plus Full scoring. Hard: RFD4 starts, SolubleMPNN/AbMPNN proposals, Full refolding, up to seven beam cycles. Ligands use Boltz binding probability plus ligand confidence. | User-defined presets, not a measured easy/hard classifier or universal success ranking. Design-time caps can stop before seven cycles. |
| Integration acceptance, Lab Books 0559 and 0574; Validation 0256 | RFD4 native/search handoffs, Full CDR-only starts and multichain target preservation have bounded technical evidence. Two-chain SUMO preparation and RFD4 refolding preserved chain sequences and MSA hashes; monomer routes produced the requested cardinality. | Small smoke tests demonstrate functioning software, not affinity, general efficacy or throughput. Multichain nanobody authoring was CPU-tested; no new multichain nanobody inference qualification. |
| Matched ESMFold2 comparison, Lab Book 0214 and docs/ESMFOLD2.md | Fast's model call was about 1.2–1.6× faster than Full at matched 3-loop/50-step settings on M4 Max, 40-core GPU, 64 GB. | Two inputs (96-residue monomer, 194-residue complex), sequence-only. Excludes loading/features/decoding. Not a campaign-speed or accuracy claim; do not reuse the old unequal-budget 4–13× comparison. |
| Motif mapping, Lab Books 0489–0491 and docs/MOTIF_BETA.md | Explicit residue-position maps are essential. Boltz's beta adapter and Protenix/IntelliFold sparse features passed CPU checks on the 41 pinned motifs. Choose the beta only for its supported benchmark inputs. | CPU feature validity does not qualify inference/cycling or enzyme activity. Only Boltz is wired to automatic cycles; Protenix/IntelliFold inference remains unqualified. The exact Artios 38-case subset is unverified. |
| Motif model/recovery smoke, Lab Book 0579; Validation 0259 | One KSI root, both ligand designers, one fixed cycle, four guided/untemplated Boltz predictions and real cancellation/replay passed. Native outputs and explicit ligand-identity receipts are retained. | One case, not all 41 or all search policies. Neither candidate passed the unchanged geometry gates. No independent-family, enzyme-activity or throughput claim; memory estimates remain uncalibrated. |
| User's failed RFD3 fixed-framework nanobody trial, 2026-10-26 | Exclude this route. Offer supported RFD4 framework design or CDR X-token workflows instead. | Do not present RFD3 fixed-framework nanobody generation as a pending feature or recommended alternative. |

## Decision rules that follow

- Protein targets: use SolubleMPNN for de-novo proteins and AbMPNN for supported
  antibody CDR proposals. LASErMPNN/LigandMPNN supply small-molecule context.
- Full accepts complete sequences and supported fixed-framework CDR-only X-token
  starts. Fast and whole-chain Full X-token generation remain unsupported.
- Structural motif conditioning, sequence-motif preservation and sparse template
  guidance are different interventions. A target template never silently becomes
  a template for the designed chain. ESMFold2 supplies no template/pocket guidance.
- Guidance/search scores are optimization feedback. Keep untemplated checks and
  different-family assessment distinct; Fast and Full are the same family.
- Boltz P(bind) + ligand pLDDT/100 is the combined ligand objective. NESSO/PSICHIC
  screening and their optional optimization objectives are distinct; do not mix
  their scores or claim validated affinity for designed binders.
- Multichain RFD4 retains the existing minimum directional ipSAE across all protein
  chain pairs, including target–target pairs. Do not describe it as binder-only.
- Memory estimates are admission estimates, not measured peaks. RFD4/guided beta
  profiles remain uncalibrated; explicit overrides are recorded and do not imply
  accuracy, reliability or a machine-independent memory guarantee.

## Find the underlying data

In a source checkout, use LAB_BOOK.md and Validation/LAB_BOOK.md to locate the
numbered entries above. Each entry names its manifest, raw outputs, audit and
untested cases. Released skill copies can use the repository sources:

- [ESMFold2 comparison](https://github.com/t-j-fryer/iProteinStudio/blob/main/docs/ESMFOLD2.md)
- [RFD4 acceptance and capabilities](https://github.com/t-j-fryer/iProteinStudio/blob/main/docs/RFD4.md)
- [Motif beta qualification](https://github.com/t-j-fryer/iProteinStudio/blob/main/docs/MOTIF_BETA.md)
- [Project Lab Book](https://github.com/t-j-fryer/iProteinStudio/blob/main/LAB_BOOK.md)

For the user's current data, use projects_list → runs_list → run_status →
results_overview before results_query. Report attempted/completed counts, exact
cycle or derivative, engine and score role, cutoff, hardware and timing scope.
Cycle 00 is not an optimized design. Include failures and avoid choosing a
favorable cycle per arm without declaring it. Unequal budgets, target subsets
or different checking models do not establish a universal engine ranking.
Local raw campaign data is not bundled with this skill or automatically uploaded.
