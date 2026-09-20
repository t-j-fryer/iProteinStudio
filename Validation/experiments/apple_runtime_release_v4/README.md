# Runtime, MSA and experimental-reference qualification

This follow-up separates three questions:

1. How close were the saved original predictions to an exact-sequence crystal?
2. Does supplying the same real MSA change the Torch runtime comparison?
3. Do the final installed app/MCP launchers run the requested runtimes correctly?

`manifest.json` declares the protocol. `crystal_compare.py` reads immutable v2
outputs and sequence-verifies the downloaded references. `preflight_msa.py`
submits each full-setting engine pair through the real Studio broker. It freezes
all Python/configuration files, the alignment, runtime/source seals and checkpoint
provenance. Never edit those frozen jobs or their completed outputs.

For the new paired tests, run each engine name once with the preflight factory:
`protenix`, `constraint`, `intellifold-flash`, `intellifold-full`. They require
v2's already prepared/sealed environments and the exact cached SUMO alignment.
There is no online MSA search or single-sequence fallback. Jobs serialize through
the shared execution lease; the coordinator resumes only audited complete blocks.

Use `audit_msa.py` after completion. It verifies receipts, exact sequences, output
counts, finite coordinates, confidence matrices, model-entry MSA shapes, and
IntelliFold's processed multi-sequence alignment. Both the original numerical
policy and the independent fixed crystal-core comparison are retained. A gate
failure is not erased by a favorable external comparison. `plot_msa.py` creates
the standalone SVG/PNG after all four paired jobs are audited.

`preflight_openfold.py` separately tests initialization work overwritten by the
checkpoint, using the original Torch2.6 runtime and a real MSA. Upstream requires
the normalized alignment basename `colabfold_main.a3m`; its unsupported-basename
attempt produced no predictions and is retained as an audit failure. This
prototype is not enabled in production by the runtime release.

After app staging and managed installation, `installed_smoke.py` exercises the
public installed `prediction_plan`/`job_start` interface for Boltz2, IntelliFold
Flash and IntelliFold Full with the same cached SUMO alignment. Boltz potentials
remain enabled. Full original model settings are retained; these are integration
checks, not new throughput measurements.

The reference structures are training-era examples, not blind test cases. SUMO
is yeast Smt3; do not substitute human SUMO1. 3QHT chain A contains the exact query
with terminal construct extensions; only observed residues 21–96 define the core.
All times in the expanded one-call MSA diagnostic are first-use times, and some
CPU compilation overlapped them. Do not publish them as isolated speedups.
