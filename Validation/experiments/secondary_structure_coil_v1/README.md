# Coil analysis and experimental harness status

## Complete and executed

`attempt_journal.py` provides domain-neutral recording of caller-supplied
artifacts and assessments. It preserves original and subsequent attempts,
enforces the original attempt budget on resume, checks stored hashes, and records
eligibility or exhaustion explicitly. It never generates candidates or executes
the next stage. Eight tests cover recovery, interrupted publication, invalid
assessments, changed budgets, corrupted artifacts and terminal-state handling.
The complete local suite now has 28 passing tests.

`diagnose.py` rechecks the completed two-arm campaign and reports per-residue
confidence, contiguous coil lengths, terminal/internal locations, original mask
and planned-strand/turn overlap, and retrospective screening outcomes. Its output
is under `Validation/output/secondary_structure_coil_v1/diagnosis/`.

`reference_bins.py` summarizes a supplied natural-reference CSV into joint
helix/sheet/coil bins, stratified by fold and structural support. It checks
assignment consistency, rejects duplicate cluster representatives and reports
unassigned residues separately. Its synthetic tests do not establish a natural
distribution. No natural cohort has been collected and no acceptance thresholds
are inferred. `research.md` describes the required cohort curation and sources.

## Draft and unrun

`seed_campaign.py` and `seed_config.json` are an unexecuted experiment scaffold.
`audit_seed.py`, `summarize_seed.py` and `monitor_seed.py` provide analysis of
declared results; their three-new-arm completion path has not run. Existing-data
checks and unit tests passed, but this is not validation of new interventions.

Adaptive cycle-00 sequence remasking and automatic entry into optimization cycles
are **not implemented**. That subtask encountered a biological-safety restriction
in the current toxin-targeted campaign. No new optimization jobs were launched.

## Reproduce the completed analysis

From the canonical repository, using the installed scientific Python:

```sh
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/secondary_structure_coil_v1/diagnose.py
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Validation/experiments/secondary_structure_coil_v1 -p 'test_*.py'
```

Reference CSV fields: `reference_id,cluster_id,origin,source,assignment_method,assignment_version,fold_class,support_class,length,helix_residues,sheet_residues,coil_residues,unassigned_residues`.
Origins and metadata are curator declarations; the binning script cannot verify
biological origin or independently folded status. Experimental B factors must not
be substituted for prediction confidence. See `research.md` before supplying a cohort.
