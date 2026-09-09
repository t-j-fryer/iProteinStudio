# Resident NESSO versus Boltz2: fluorescein scoring

This experiment compares the production scoring paths on 50 frozen protein
sequences from the original `nise_fluorescein` campaign (not its v2 successor).
It measures steady-state wall time and exploratory score/rank agreement.
It does not establish experimentally accurate binding or replace Boltz coordinates.

Selection uses 50 evenly spaced ranks of the historical P(bind)+ligand pLDDT/100
score, including both endpoints, after excluding missing/nonfinite scores,
initialization, noncanonical sequences and duplicate sequences (first occurrence
wins). Sequence-designed Phase 0 outputs can be included; masked cycle00 cannot.
Selected structures, input YAMLs, confidence and affinity files are copied and
hashed, and protein sequences/coordinates are audited. Related sequences are not
50 independent lineages. Selection is enriched across the old score range.

Both methods receive identical sequences and the Boltz-affinity-standardized
fluorescein hydroxyethylamide chemical state. No backbone is supplied as a template.
Boltz uses an empty MSA, physical potentials, no pocket restraint, 3 recycles,
200 diffusion steps, one structure sample and its affinity head. NESSO uses its
pinned refined 5-recycle float32 MPS protocol and fresh ESM-2 embeddings.
Model architectures and work differ: these are fixed native production settings,
not equal diffusion/FLOP budgets. Boltz’s affinity head separately uses its native 5 recycles, 200 diffusion
steps and 3 samples; these defaults are frozen by source provenance. Historical predictions select cases only; they are not
reused as the fresh timing control. Early historical pocket restraints are
recorded but are not applied to either side of this unconstrained scoring test.

A separate three-case pilot (low/middle/high historical score) must finish and
pass the output audit before the 50-case plan can be created. Each model has a
separate exclusive resident session, with one excluded warmup request before
measurement. NESSO holds NESSO and ESM; Boltz caches structure and affinity models.
No second GPU worker runs concurrently. Fresh ESM, preprocessing, prediction,
affinity and normal pipeline output/geometry checks are included in wall time;
experiment integrity hashing and model startup are excluded and separately
recorded. There is one measured pass per model; there are no independent timing
replicates or randomized thermal-order claims.

Atomic receipts hash every raw output before reuse. Interrupted attempts are
retained and new attempts use new directories; a new worker always warms up.
Session identities and load counts expose any reloads. Every inference runs
through the Studio immutable preflight plan and exclusive execution broker,
following the existing `nise_integration_v1` validation pattern. No global runtime
code or live design configuration is replaced.

```bash
ROOT="${NANOHUNTER_ROOT:-$HOME/.iproteinstudio}"
EXPERIMENT=Validation/experiments/nesso_boltz_fluorescein_v1
OUT=Validation/output/nesso_boltz_fluorescein_v1
"$ROOT/venvs/NanoHunter_boltz/bin/python" "$EXPERIMENT/campaign.py" prepare --output "$OUT" --source /path/to/original/nise_fluorescein
python3 "$EXPERIMENT/campaign.py" plan --output "$OUT" --phase pilot
# Use the returned ID and digest:
python3 "$ROOT/mcp/studioctl.py" start PLAN_ID PLAN_SHA256
# After the pilot is complete and its audit passes:
python3 "$EXPERIMENT/campaign.py" plan --output "$OUT" --phase full
python3 "$ROOT/mcp/studioctl.py" start PLAN_ID PLAN_SHA256
```

NESSO primary rank is P(bind)+(1−entropy_crop_pl). Missing, nonfinite,
out-of-range or <=1e-6 entropy is rejected, never converted to perfect confidence.
Report NESSO binding probability, cropped and full placement entropy separately,
Boltz binding probability, ligand pLDDT, combined score and affinity outputs.
Correlations are descriptive for a selected, related, single-ligand cohort.

## Completed result

On the M4 Max/64 GB machine, 50 paired cases passed. NESSO+ESM averaged 10.452 s
versus 64.357 s for Boltz2+affinity (6.157× ratio). Combined-score Spearman ρ = 0.106;
NESSO top 20 retained4/10 Boltz top-ten designs. This is faster scoring with weak
agreement, not validation of NESSO as a Boltz ranking replacement. The original
IntelliFold Full batch was resumed after the benchmark.

[Full report](../../output/nesso_boltz_fluorescein_v1/analysis/REPORT.md),
[overview](../../output/nesso_boltz_fluorescein_v1/analysis/overview.svg),
[Validation Lab 0024](../../lab_book/0024-resident-nesso-boltz-fluorescein.md).
The report generator is archived and hashed alongside the derived outputs.

```bash
python3 Validation/experiments/nesso_boltz_fluorescein_v1/analyse.py --output Validation/output/nesso_boltz_fluorescein_v1
python3 -m unittest discover -s Validation/experiments/nesso_boltz_fluorescein_v1 -p 'test_*.py'
```
