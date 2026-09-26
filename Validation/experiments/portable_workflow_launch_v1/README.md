# Portable workflow launch acceptance

This is software integration acceptance on the recorded M4 Max, not a speed or
design-quality comparison. The natural target is SUMO, with its existing cached
MSA. Small-molecule tests use biotin. No student target or student structure is
used. The matrix and every submitted request are in `manifest.json`.

The existing production biotin job was stopped through the public broker before
testing. Its immutable plan and runtime bindings are retained. Checkpoint hashes
are compared before stopping, after stopping and after the final resume.

`prepare_design_cases.py` prepares an isolated managed project and declares tiny
budgets. `control.py submit CASE ...` reads the public workflow guide, creates a
managed plan and starts its immutable digest. Existing plans/jobs are reused,
never silently resubmitted. RFdiffusion3 inputs also pass `target_inspect`.
`control.py status` captures job diagnostics; `control.py overview` reads the
grouped managed results. Run with the installed control Python. New fixed-plan
attempts get new case IDs; failed outputs remain untouched. The source-bridge
override is explicitly recorded when used to test a planner fix before staging.

`audit.py` runs on CPU in the managed Protenix/Biotite environment. It checks
output cardinality, finite coordinates, requested SUMO and cycle sequences,
confidence JSON and visible progress instrumentation. Raw outputs and execution
receipts stay under the managed test project and ignored
`Validation/output/portable_workflow_launch_v1/`; this directory contains the
reproducible harness and declarations, not model weights.

One trajectory/backbone and one redesign cycle bound the ordinary cases. Predict and Protein Hunter request one sample; RFdiffusion3 verification retains each adapter's sample default. The Boltz NISE retry uses three starts after the single candidate failed its structural gate. Diffusion
steps, recycles, precision and guidance defaults are not reduced. Disposable NISE
cases use zero score gates to exercise the later scoring/selection code; these
are diagnostic overrides, not proposed scientific defaults. A low-scoring design
is not a failed launch. Fresh-Mac, other-chip, large-input memory and long-campaign
acceptance are outside this matrix.

The discovered portable activation defect is recorded in project Lab Book 0198.
Full execution, additional failures/fixes, release and resume evidence are tracked
in project Lab Book 0199 and Validation Lab Book 0052.
