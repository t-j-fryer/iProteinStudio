# Helix strength across seven engines, geometry recorded without rejection

Fresh, paired 90-aa monomer benchmark: strengths 0, 0.5, 1; ten trajectories and five optimization cycles each. Same declared seeds as v2; previous raw outputs remain preserved and are not pooled into v3. Every condition runs one audited pilot before its remaining nine trajectories. Cycle00 is excluded from structural endpoints.

Geometry distance thresholds are diagnostics only at every cycle. Each normalized prediction has a geometry_report.json with atom pair, residues, distance, threshold and coordinate SHA256. Unreadable/nonfinite/empty coordinates remain operational failures. Audits remeasure geometry independently, verify the report, retain violations in structural endpoints, and export geometry_by_cycle.csv. No failed seeds are replaced.

Use campaign.py stage, prepare, run with the managed Python through Studio. Source bytes are frozen in output/source, model and engine inventory in stage_receipt.json, and plans/jobs retain bridge provenance, GPU lock, MSA and scheduler checks. Concurrent deployed runtime changes fail verification; original outputs are never rewritten. Final report/contrasts/figures run in the controller after all audited outcomes.
