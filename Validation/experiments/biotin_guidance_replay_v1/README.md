# Biotin guidance and request grouping

Replay the 30 completed cycle00 inputs from the paused 1000-start NISE campaign.
These are initial X-containing backbones, not optimized designs. The source job
and all original raw outputs remain unchanged.

The comparison retains exact sequences, seed0, empty MSA, 3 recycles, 200
diffusion steps, one output sample, FP32/MPS, and the forced pocket restraint.
Physical/FK guidance is disabled; contact guidance remains enabled. No affinity
head is run. One resident model handles each arm, then closes before the other
arm starts. All-input submission is one Boltz CLI invocation with the normal
data-loader batch size1, not parallel folding of30 inputs.

The first two-input pilot correctly stopped because the second input's actual
features changed: unseeded RDKit conformer generation advances independently of
the Boltz seed. The corrected experiment freezes each original processed input,
including ligand conformer and constraints. Singleton Python/NumPy/CPU/MPS RNG
states are captured without reseeding at feature and prediction boundaries;
the directory arm restores each input's states. Model tensor hashes must match.
No claim of bitwise-identical MPS output is made; coordinates and confidence are
compared independently. This instrumentation is specific to the benchmark.

## Reproduction

Set `NANOHUNTER_ROOT` to the managed installation, then run installation detection.
Pause the source through `job_cancel` and wait for terminal status. Create a
two-input pilot with:

```sh
python3 Validation/experiments/biotin_guidance_replay_v1/prepare.py \
  --source-job JOB_ID --limit 2 \
  --records Validation/output/biotin_guidance_replay_v1/pilot
```

Launch the saved immutable `plan.json` through the shipped MCP bridge's
`job_start`, supplying its ID and SHA256. After the pilot passes, run `prepare.py`
without `--limit` in a new records folder and launch that reviewed plan. No direct
model launch outside the broker is supported. The private typed desktop route
records script, model, CCD and input provenance and obtains the shared GPU lock.
Resume through the broker: completed units are hash-audited, while an interrupted
directory request is preserved separately and restarted as a whole. Timing
analysis deliberately rejects multiple worker sessions rather than silently
mixing resumed and uninterrupted timings.

Audit and report with the managed Boltz Python:

```sh
"$NANOHUNTER_ROOT/venvs/NanoHunter_boltz/bin/python" \
  Validation/experiments/biotin_guidance_replay_v1/analyse.py \
  --output REPLAY_OUTPUT --report ANALYSIS_OUTPUT
```

Generate figures in the already installed plotting environment:

```sh
"$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" \
  Validation/experiments/biotin_guidance_replay_v1/analyse.py \
  --plot-audit ANALYSIS_OUTPUT/audit.json --report ANALYSIS_OUTPUT
```

## Interpretation

Time is request wall time per completed initialization, including feature/RNG
instrumentation and output checks, with model startup listed separately. The
original baseline includes initial YAML/RDKit preprocessing; both replay arms
reuse the original processed inputs. Do not attribute that entire contrast to
potential evaluation alone. Batch wall time is one measurement divided by30;
there are no30 independent batch wall-time observations.

Geometry uses the production contact/exposure checks and backbone-continuity
diagnostics. Severe overlaps are heavy-atom van der Waals overlaps greater than
1 Å; protein self-pairs exclude the same and neighboring residues. This is a
descriptive diagnostic, not MolProbity clashscore. Ligand bond lengths use RDKit
distance-geometry bounds plus0.15 Å tolerance; named stereocentres are checked
from coordinates against SMILES. No Ramachandran, rotamer or energetic validation
is claimed. X residues lack full side chains, and none of these metrics establish
binding. One ligand, fixed order, no timing repeats or default promotion.

The full NISE campaign remains paused pending review of the comparison.

## Independent chirality checks

The main audit compares coordinate-derived CIP labels with the input SMILES,
then checks signed tetrahedral volumes against each actual frozen input
conformer. All270 assessed ligand centres agree between these methods. An
additional protein-Cα cross-check is reproducible with:

```sh
"$NANOHUNTER_ROOT/venvs/NanoHunter_boltz/bin/python" \
  Validation/experiments/biotin_guidance_replay_v1/crosscheck_protein_chirality.py \
  --audit ANALYSIS_OUTPUT/audit.json \
  --output ANALYSIS_OUTPUT/protein_chirality_crosscheck.json
```

Protein checks exclude glycine and residues without CB, including X/UNK. No
reversed assessable protein Cα centres were found; one nearly planar centre
appears in each pocket-only arm. This does not establish complete stereochemical
or conformational validity of the protein.
