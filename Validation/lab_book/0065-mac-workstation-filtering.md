---
entry: 0065
title: Compare completed Mac scores with workstation filtering
date: 2026-09-30
status: complete; interim Boltz and IntelliFold Flash only
---

Experiment `experiments/mac_workstation_filtering_v1`; declaration precedes calculations. Outputs `output/mac_workstation_filtering_v1/snapshot_20260930`. No new predictions; original source data and ongoing GPU job unchanged.

674 unique design-name pairs each, audited target hashes/lengths and binder lengths; workstation lacks binder sequences. Fixed clean563/85-hit cohort, strict550 cohort, primary-screen endpoint and assayed-sequence sensitivity. Original assay label sets independently recomputed and matched. Workstation original F2 AP independently reproduced exactly. Four actual ranking/tie/AP/zero-hit checks and visual figure review pass.

Boltz F2AP0.367→0.375 and hits/top5018→24; Flash0.394→0.384 and20→21. Paired bootstrap intervals span zero and several AP points of degradation. ipSAE rank correlations0.913/0.920. SUMO shows lower AP in both Mac arms. Threshold transfer notably changes Boltz recall. Figures/tables preserve all comparisons, failures of comparability and no-hit Myc undefined metrics.

No attribution solely to MSA/steps: potentials, sample count/aggregation and undocumented workstation runtime/score implementation confound. OpenFold is not openDDE. No materiality margin predeclared; no equivalence claim. Runtime forecast about22h central,14–32h planning range from actual qualification means plus orchestration allowance; exact timestamp in progress_eta.json. No other-chip, prospective biological or family-bootstrap testing. Project0233 contains commands and details.
