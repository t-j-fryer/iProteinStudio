# Audit of the three test2 NISE runs

Audited 16 September 2026. This is a read-only reconstruction from saved requests,
candidate JSON, screening/atom-check CSVs, job state/logs, frozen NISE source, and
RFdiffusion3 fixtures and logs. No models were run and no campaign data were edited.
Machine context: local Studio installation on the project's M4 Max / 64 GB Mac;
hardware utilisation and sleep were not independently recorded by this audit.

## Outcomes

| Saved name | Outcome | Initial structures completed | Subsequent sequence-bearing Boltz folds | Recorded execution wall span |
|---|---|---:|---:|---:|
| NISE_BOLTZ_PH_Bt | Completed; two trajectories reached the later ligand-consistency stage | 100 | 2,369 | 61 h 8 min |
| NISE_NESSO_PH_Bt | No candidates survived the initial structural gate | 100 | 127 | 6 h 29 min |
| NISE_NESSO_RFD_Bt | RFdiffusion3 metrics code crashed on an empty optional selection | 0 audited/exported; two partial raw PDBs exist | 0 | 2 min 19 s |

These durations are job `started_at` to `finished_at`, excluding the preceding
queue wait. They are **not GPU compute times or a speed benchmark**. Workloads,
stopping points and starting coordinates differ. Exact timestamps, requests and
derived counts are in [audit.json](audit.json); [audit.py](audit.py) regenerates it.

Run identities, under `~/.iproteinstudio/projects/test2/nise_runs/`:

- Boltz/PH: `nise-C9CCE180-9E41-4BA3-95AE-CB03FBB867FA`, job `job-4a2f043a9b21`.
- NESSO/PH: `nise-016073B9-7F59-4E71-BBA3-62ACDEFBD44C`, job `job-583a358c6eb5`.
- NESSO/RFD3: `nise-CC39D6E2-90C1-4A59-B32B-D597A15D45C4`, job `job-bbc773b52ca2`.

## Shared setup and meaning of the checks

All three requested 100 starts, lengths 65–150, and up to six NISE trajectories.
They used the same input ligand and atom-map signature. The standardized SMILES
recorded by the runtime was `O=C(O)CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21`.

- **Bind:** C31, S20, C29, C32, N24, C30, N23, O17, C21;
  each required a protein contact within 6 Å.
- **Expose:** C25, C22, O18, O19; each required at least 50% of its isolated-ligand
  solvent-accessible area in the same ligand conformation.

The settings were actually applied: the candidate records contain distances and
per-atom accessibility rejections, and the RFD3 fixtures contain nine hotspots and
four exposed atoms. This audit does not suggest that the atom controls were ignored.

Initial cycles 01/02 generated three LASErMPNN sequences per surviving lineage,
folded with pocket restraints and selected the best atom-check-passing sequence.
There was no backbone RMSD gate in these two refinement rounds. Initial cycle03
removed the pocket restraint and required Cα RMSD **<2 Å** against the previous
structure, plus all atom checks. Initial cycle04 expanded gate survivors with five
sequences each, then selected at most one seed per original lineage.

During NISE optimisation, the saved configuration generated 64 sequences per
parent, beam size one, maximum 30 cycles and patience five. Cα RMSD **<2.5 Å** was
required throughout; ligand RMSD **<2.5 Å** became mandatory at optimisation
cycle03. These RMSDs are self-consistency checks against saved parent structures,
not agreement with an experimentally determined complex.

## Initial-stage attrition

| Stage | Boltz/PH | NESSO/PH |
|---|---|---|
| Initial cycle00 | 100 starts | 100 starts |
| Initial cycle01 | 300 folded; 54 pass atoms; **40 lineages advance** | 300 NESSO-scored, 100 folded; 18 pass atoms; **18 advance** |
| Initial cycle02 | 120 folded; 24 pass atoms; **21 lineages advance** | 54 NESSO-scored, 18 folded; 3 pass atoms; **3 advance** |
| Initial cycle03 gate | 63 folded; 6 pass all checks from **5 lineages** | 9 folded; **0 pass** |
| Initial cycle04 expansion | 30 folded; 10 pass atoms; **5 seeds selected** | Never reached |

Six individual gate survivors produced the 30 expansion sequences, although those
six came from only five distinct original lineages. The five-seed result therefore
respects the one-per-lineage rule; the requested six was an upper limit.

## NISE_BOLTZ_PH_Bt: completed, with an output interpretation problem

This run performed 100 initial hallucination folds plus 2,369 sequence-bearing
folds: 513 in initial refinement/gating/expansion and 1,856 in NISE optimisation.
It ended normally, exit code zero. Thirty cycles was a ceiling, not a promise:

- T2/L031, T3/L039 and T4/L025 stopped at optimisation cycle03. None of their
  64 candidates per trajectory passed the newly active ligand RMSD threshold.
- T0/L051 improved through cycle04, then stopped after five consecutive
  non-improving cycles, at cycle09.
- T1/L001 improved through cycle06, then stopped after five consecutive
  non-improving cycles, at cycle11.

Boltz ranking was `ligand_pLDDT / 100 + P(bind)`. The exported historical winners are:

| Export | Winning candidate | Score | Ligand pLDDT | P(bind) | Cα / ligand RMSD (Å) | Ligand consistency required when selected? |
|---|---|---:|---:|---:|---|---|
| rank0_T1_L001.pdb | c06_t1_n0_s58 | 1.435 | 91.06 | 0.525 | 0.793 / 0.949 | Yes |
| rank1_T0_L051.pdb | c04_t0_n0_s43 | 1.344 | 88.46 | 0.459 | 0.413 / 1.101 | Yes |
| rank2_T3_L039.pdb | c01_t3_n0_s52 | 1.126 | 84.71 | 0.279 | 0.833 / 8.868 | **No** |
| rank3_T2_L031.pdb | c02_t2_n0_s7 | 1.015 | 73.21 | 0.283 | 1.943 / 6.148 | **No** |
| rank4_T4_L025.pdb | c01_t4_n0_s5 | 0.758 | 65.44 | 0.103 | 2.351 / 2.566 | **No** |

The first two are the strongest candidates to inspect next by this run's own
criteria. The other three are **historical early-stage winners**, preserved even
though their trajectories later died. Their `passed` flags mean they passed the
checks active in their cycle; they did not pass the later ligand-pose criterion.
Treating all five exports as equally qualified final hits would be misleading.
This is an output qualification/labeling problem, not evidence that the cycle03
filter failed to run.

Preorganisation was disabled, so there is no apo-fold confirmation in this run.
These are model-ranked candidates, not experimentally validated binders.

## NISE_NESSO_PH_Bt: exhausted candidates, rather than a model crash

The pipeline exited explicitly because the initial gate had no survivors. It never
reached initial expansion or NISE optimisation. The saved request enabled NESSO
there too, but those later settings were never exercised.

NESSO scored 354 refinement sequences; 352 were eligible and two were rejected by
the near-zero-entropy guard. It selected 118 sequences for Boltz folding: one per
lineage in each refinement round. The recorded ranking formula was exactly
`P(bind) + (1 - entropy_crop_pl)`, policy `nesso-pbind-placement-v2`. Saved selected
scores agree with that formula.

The major initial rejection pressure was solvent exposure. At initial cycle01,
65/100 folded candidates failed C25 exposure, 59 failed O19, 57 failed O18 and
56 failed C22 (overlapping counts). Only one failed a hotspot distance check.
NESSO's sequence/ligand score does not itself enforce these geometric conditions;
they are evaluated after folding.

At the final initial gate, **all nine candidates failed the 2 Å backbone threshold**:

| Candidate | Cα RMSD (Å) | Atom checks pass? |
|---|---:|---|
| L004_c3_0 | 4.246 | No |
| L004_c3_1 | 3.161 | No |
| L004_c3_2 | 3.220 | No |
| L018_c3_0 | 6.327 | No |
| L018_c3_1 | 4.533 | Yes |
| L018_c3_2 | 5.338 | Yes |
| L021_c3_0 | 3.285 | No |
| L021_c3_1 | 18.052 | No |
| L021_c3_2 | 3.060 | Yes |

Relaxing exposure alone would therefore not rescue this gate. The last progress
message, `Completed L021_c3_2`, describes one prediction, not campaign success;
the broker state and terminal log correctly record failure.

Selecting one of three sequences before folding plausibly reduced survival
opportunities: both runs had an 18% atom-pass rate per fold in initial cycle01,
but the three-folds-per-lineage run retained 40 lineages versus 18. This is an
observation, not proof that NESSO caused the failure: none of the 100 initial
reference PDBs had identical coordinates across the two runs, and their sampled
sequences also differed. The upstream sequence sampler has no seed control.

Among the NESSO-selected sequences with paired Boltz scores, composite-score
Spearman correlation was 0.111 (n=100, initial cycle01) and 0.143 (n=18, cycle02).
Pearson correlation was 0.160 and 0.428 respectively. These are **selected subsets**,
with no Boltz measurements for the rejected alternatives; they cannot establish
unbiased screening performance, causal superiority, or speedup.

## NISE_NESSO_RFD_Bt: concrete RFdiffusion3 software defect

Preparation succeeded: atom names resolved, and fixtures were created for lengths
65, 86, 108, 129 and 150. Generation then failed in both length-65 workers:

```text
ValueError: zero-size array to reduction operation minimum which has no identity
```

The traceback identifies `rfd3/scripts/generate_backbones.py:298`, in
`Fixture.metrics()`. It calculates `d.min()` for both buried and exposed atom
subsets without checking whether each optional subset contains any atoms.

The actual fixtures contain **16 fixed ligand atoms, nine hotspots, four exposed
atoms and zero buried atoms**. That is a valid request: hotspot contact does not
mean explicitly buried. The empty buried subset triggers the reduction error.
The installed script's SHA-256 agrees with the failed job's recorded provenance:
`29ec54f9c46c4b78a5ae33921046ebe3cf8b1f33cdc13c813f719bd22fca0f52`.

Two raw `design_0001.pdb` files were written before metrics calculation crashed.
Both batch-state files report zero accepted/attempted and no completed file records;
these are partial artifacts, not a completed two-backbone campaign. No LASErMPNN,
NESSO or Boltz stage was reached. Thus this failure says nothing about NESSO quality
and is not an invalid atom-number or missing-model error.

The appropriate code fix is to handle empty optional subsets explicitly in the
metrics calculation. Adding artificial buried-atom requirements to avoid the
crash would change the scientific request and is inappropriate.

## Follow-up priorities

1. Repair and regression-test empty buried/exposed metric subsets in RFdiffusion3,
   then perform a small managed end-to-end smoke run with this exact conditioning
   before launching another 100-backbone campaign. Do not rewrite frozen old runs.
2. Distinguish historical bests from candidates that passed the final active
   consistency criteria in exports and the app. Also make terminal campaign failure
   supersede stale per-candidate progress messages.
3. If comparing NESSO shortlist sizes, reuse a fixed recorded set of backbones and
   sampled sequences. Compare one versus two/three sequences advanced per lineage,
   recording geometry-pass rate and lineage retention as well as score correlation.
   This audit does not justify weakening structural/exposure thresholds.

## Evidence and reproduction

Within each run: `nise_config.json`, `candidates/*.json`, `atom_checks.csv`,
`phase0/`, `progress.json`; additionally `summary.json`, `best/` and
`trajectory.csv` for the completed run, and `nesso_screening.csv` for NESSO/PH.
Broker evidence: `~/.iproteinstudio/agent/jobs/<job-id>/{state.json,pipeline.log,plan.json}`.
RFD3 evidence: `phase0/cycle00/rfd3_initial/design.yaml`, `rfd3/fixtures/*.npz`,
and length-65 queue logs and `batch_state.json` files. Frozen NISE control flow:
`.studio_runtime/pipeline/scripts/nise/{nise_run.py,rfd3_initial.py}`.

```bash
python3 lab_book/artifacts/0131-test2-nise-audit/audit.py \
  --runs "$HOME/.iproteinstudio/projects/test2/nise_runs" \
  --jobs "$HOME/.iproteinstudio/agent/jobs" \
  --output /tmp/test2-nise-audit.json
```

The script requires NumPy and performs no inference. Counts come from candidate
records rather than trajectory CSV row counts, which only contain selected or
passing records. This audit did not independently recompute structures, affinities,
RMSDs or solvent-accessible surfaces; it checked the recorded evidence and control
flow. It did not validate binding, solubility, expression or experimental utility.
