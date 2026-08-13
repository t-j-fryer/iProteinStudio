# Instructions for AI agents

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
- **Never commit weights**, and never redistribute AlphaFold 3 parameters.
- **No absolute paths from your own machine** in shipped code. Derive roots from
  `NANOHUNTER_ROOT` or from the script's own location.
- `swift build` must pass before you commit.

## Running things

See `docs/CLI.md`. Start with `bash "$ROOT/setup_pipeline.sh" --detect` and never
assume an engine is installed.

## Scope

NISE stays in NanoHunter. RFdiffusion3 against DNA/RNA is out of scope — the
nucleic-acid checkpoint is not obtainable. Do not wire either in without being
asked.
