# Instructions for AI agents

## Repository authority

`/Users/thomasfryer/iProteinStudio` is the canonical and only active Studio
repository. Do not inspect, edit, test from, or create worktrees under the
legacy `NanoHunterStudio` checkout unless the user explicitly asks for it.
Linked development worktrees must live under
`/Users/thomasfryer/iProteinStudio/.worktrees/`.

This file is for any coding agent (Codex, Cursor, Copilot, and others). Claude
Code should read `CLAUDE.md` first, which is more detailed; the skill at
`.claude/skills/iprotein-run/` covers running the pipelines.

## What this is

iProteinStudio is a native macOS front end to an Apple-Silicon protein design and
structure-prediction suite. It contains almost no science of its own: the science
lives in sibling repositories, and this app makes it reachable and hard to
misuse. When a capability exists upstream, **port the validated behaviour — do
not reinvent it, and do not silently diverge from its defaults**.

## Standing requirements

1. **Reproducible.** A run must be re-creatable from what is on disk. No silent
   fallbacks: if a requested alignment, weight file or model is missing, fail
   loudly rather than substituting something weaker.
2. **Robust.** Long campaigns get interrupted. Checkpoint per unit of work and
   make every stage resumable.
3. **Optimised for Apple Silicon**, using *measured* settings. Every performance
   claim must trace to a Lab Book entry with numbers.
4. **Noob-proof.** The user is a bench scientist who has never opened a terminal.
   Constrain nonsense in the UI, not in a warning in the docs.

## Non-negotiables

- **Record your work in the Lab Book.** `lab_book/NNNN-slug.md` from the template,
  indexed in `LAB_BOOK.md`. Include what you did not test.
- **Never state a benchmark number you did not measure**, or copy one without
  saying where it came from and on what hardware.
- **A syntax check is not a test.** `py_compile` has passed on code with an
  undefined name and a call to a script that did not exist. Run it.
- **Never commit or redistribute model weights.**
- **No absolute paths from your own machine** in shipped code. Derive roots from
  `NANOHUNTER_ROOT` or from the script's own location.
- `swift build` must pass before you commit.

## Running things

See `docs/CLI.md`. Start with `bash "$ROOT/setup_pipeline.sh" --detect` and never
assume an engine is installed.

For MCP-driven work, call `workflow_guide` before a scientific plan. Protein
de-novo binders default to SolubleMPNN; LASErMPNN/LigandMPNN are restricted to
small-molecule interfaces. Omit the protein de-novo contig so Studio derives it,
complete a 1–5-backbone end-to-end smoke run before a new campaign over 10, and
diagnose `job_status.error`/`pipeline_log_tail` before changing settings or
requesting arbitrary filesystem access.

For Codex, Claude Code, or another MCP client, use the shipped client-neutral
bridge under `$ROOT/mcp/`. Keep the `read`, `run`, and normally disabled `admin`
profiles separate. Expensive work must go through a preflight plan and
`job_start`; do not bypass the bridge's immutable plan digest, script-provenance
check, shared execution lock, MSA policy, or recorded resident/cycle-wave
scheduler. See `docs/CLI.md#ai-agents-model-context-protocol`.

## Validation campaigns

Performance and settings experiments belong under `Validation/`. Read
`Validation/AGENTS.md` before touching that tree. Every campaign must have a
declared manifest, immutable raw outputs, an output audit, and an entry in both
the Validation Lab Book and the project Lab Book before a setting is promoted.

## Scope

NISE stays in NanoHunter. RFdiffusion3 against DNA/RNA is out of scope — the
nucleic-acid checkpoint is not obtainable. Do not wire either in without being
asked.
