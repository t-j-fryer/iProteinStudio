# SUMO resident model matrix

Nine installed sequence-to-structure models;250 primary predictions and50 independent profiling replays. See manifest.json for predeclared scientific settings. Five seeds42–46, one sample, fixed96-aa yeast Smt3. No-MSA, frozen128-row alignment, full cached8060-row alignment; ESMFold2 Fast is sequence-only. Native steps versus approximately one-eighth, rounded to supported integer requests; native recycles and profiles retained.

One immutable broker-owned campaign runs one model-owning process per engine, sequential requests to the retained instance. No independent GPU launch or downloads. Exact-token sizing is the explicitly requested app policy change; diffusion/MSA/recycle defaults remain unchanged. Each request records PID, model load count, scientific settings, input feature shapes when exposed, memory, total request wall, CPU time, preprocessing, featurization and GPU-synchronized model wall. First request is marked. Five normal predictions are separated from one synchronized stage diagnostic at seed42 per condition. Nested diagnostic stages must not be summed. Cold session initialization and imports/setup are recorded once, rather than incorrectly charging model reload to each request.

The installed broker may canonicalize dictionary ordering in its execution configuration; read actual unit timestamps/logs for execution order. Within each engine, conditions are none,128,full; full then reduced steps. This fixed ordering and one short target limit causal/generalized performance claims. Seed variation includes model RNG and native feature sampling. Full MSA preserves native caps, not an assertion that every model processes all8060 rows.

Preparation: `campaign.py prepare`, then review output plan and call installed `job_start` with its immutable id/digest. Do not overwrite partial output; any repair uses a newly frozen retry plan/directory. Run the following CPU analysis using the existing analysis environment:

```sh
MPLCONFIGDIR=/private/tmp/sumo-matrix-mpl OPENBLAS_NUM_THREADS=1 Validation/output/esmfold2_mlx_update_v1/venv/bin/python Validation/experiments/sumo_model_matrix_exact_v1/analyse.py
MPLCONFIGDIR=/private/tmp/sumo-matrix-mpl OPENBLAS_NUM_THREADS=1 Validation/output/esmfold2_mlx_update_v1/venv/bin/python Validation/experiments/sumo_model_matrix_exact_v1/plot_stages.py
```

Quality: exact query sequence, complete backbone, finite coordinates, Studio geometry advisories, crystal3QHT chainA fixed query residues21–96. Kabsch core fit, core CA-RMSD, core CA-lDDT, native pTM/pLDDT and all core-aligned PDBs. The mobile N terminus is retained in exported structures but excluded from the primary quality calculation. This may be a training-era structure and cannot rank broad model accuracy. No monomer ipSAE/iPTM interpretation.

Outputs: `Validation/output/sumo_model_matrix_exact_v1/{REPORT.md,OVERVIEW.svg,STAGES.svg,LOADING.svg,analysis/results.json,analysis/measurements.csv,analysis/aligned/}`. See project Lab Book0227 and Validation0059. Biotin stays paused.

This continuation repeats Full and Flash with exact input token dimensions and runs the four outstanding engines. Boltz/ESMFold2 outputs are reused from sumo_model_matrix_v1 via explicit reuse_engine_outputs paths in the frozen config. CLI acceptance at intellifold_exact_cli_v1 separately covers96,97 and103 protein tokens, both models, normal app launcher defaults, all six finite/complete with geometry violations0. The policy module is frozen with the benchmark and preloaded into the resident adapter; the prepared runtime snapshot predates app staging but therefore uses the same exact-size policy.
