# Working rules for AI agents on NanoHunter Studio

Read this file, then read [`LAB_BOOK.md`](LAB_BOOK.md) before doing anything else.
The Lab Book is the project's memory. This file is how you are expected to behave.

## What this repo is

NanoHunter Studio is the **native macOS front end to our whole Apple-Silicon protein
design tool suite**. It is a SwiftUI app. It contains almost no science of its own:
the science lives in sibling repositories, and this app's job is to make that science
reachable, reproducible and hard to misuse for someone who has never opened a terminal.

The sibling repos and what we take from each:

| Repo | Path on the dev machine | What Studio uses it for |
|---|---|---|
| NanoHunter / iProteinHunter | `/Users/thomasfryer/NanoHunter` | The iterative design runner (`nanohunter_run.sh`), all four structure predictors, every MPNN/AntiFold designer, MSA handling, device calibration |
| RFD3 | `/Users/thomasfryer/RFD3` | RFdiffusion3 backbone generation on MLX, ligand conditioning, length-binned batching |

Those repos are the **upstream source of truth for the science**. When Studio needs a
capability that exists there, port the *validated* behaviour — do not reinvent it, and
do not silently diverge from its defaults.

## The four standing requirements

Every change is judged against these. They come from the project owner and they do not
expire.

1. **Reproducible.** A run must be re-creatable from what is recorded on disk. Never
   let a setting reach a model without it being written down somewhere the user can
   find. No silent fallbacks — if a requested MSA, weight file, or model is missing,
   fail loudly rather than quietly substituting something weaker.
2. **Robust.** Long campaigns get interrupted. Checkpoint per unit of work, make every
   stage resumable, and treat "the machine slept for six hours" as a normal event.
3. **Efficient and optimised for Apple Silicon.** Use the *measured* settings, not
   plausible-sounding ones. Every performance claim in this repo must trace to a
   Lab Book entry with numbers. See `lab_book/0002-inherited-speed-lessons.md`.
4. **Aesthetic, user-friendly, noob-proof.** The target user is a bench scientist who
   has never used a terminal. Defaults must be safe and good. Options that can produce
   nonsense must be constrained by the UI, not by a warning in the docs. Prefer
   removing a choice over explaining it.

## Recording your work — mandatory

**Any AI that works on this repo records what it did in the Lab Book.** This is not
optional and it is not a formality: the next agent inherits nothing but this repo, and
an undocumented decision will be undone by someone who does not know why it was made.

Before you finish a piece of work:

1. Create `lab_book/NNNN-short-slug.md` from `lab_book/TEMPLATE.md` (next free number).
2. Fill in every section. If a section genuinely does not apply, write `n/a` and why —
   do not delete it.
3. Add a one-line pointer to the index in `LAB_BOOK.md`, newest first.
4. If the change altered project status, update the **Current status** block at the top
   of `LAB_BOOK.md`.

What earns an entry: any experiment or benchmark, any design decision with a real
alternative, any dependency or version pin, any bug whose cause was non-obvious, any
port of behaviour from a sibling repo, any performance claim.

What does not: typo fixes, formatting, mechanical refactors that change no behaviour.

Write entries so they are useful when they are wrong. Record what you measured, what
you assumed, what you did not test, and what would falsify the conclusion. **Negative
results are worth as much as positive ones** — an entry saying "we tried X, it was
4% slower, here is the command" prevents someone spending a day on X again.

## Honesty rules

- Never state a benchmark number you did not measure on this machine, or copy from a
  sibling repo without labelling where it came from and on what hardware.
- If a feature is present in the UI but not actually validated end to end, say so in
  the entry and gate it in the UI.
- If you could not finish something, write the entry anyway describing where you got to
  and what blocked you. A half-finished, well-documented attempt is a useful inheritance.
  A half-finished silent one is a trap.

## Practical conventions

- **Hardware.** All timings recorded here are Apple M4 Max, 40-core GPU, 64 GB unified
  memory, macOS 26.x, unless the entry says otherwise. Always state the machine.
- **Long jobs.** Wrap anything multi-minute in `caffeinate -dimsu`. Launch genuinely
  long campaigns detached, not as a plain background command that dies with the shell.
- **Benchmarking.** Refuse to benchmark while another Boltz/IntelliFold/RFD3 process is
  using the GPU. Use wall time per completed unit of work, not per-job duration —
  contention makes individual jobs look slow while total throughput improves.
- **Memory.** Judge feasibility by macOS *physical footprint* and live available memory,
  never by RSS alone. Keep a reserve so the user's machine stays usable.
- **Local vs. distributed installs.** On this machine, reuse the already-installed
  NanoHunter and RFD3 rather than duplicating multi-GB environments. For anyone else,
  the install path must work from a clean checkout. Both must be true at once.
- **Weights are never committed.** AlphaFold 3 parameters in particular are governed by
  Google's terms and must not be redistributed. `models/` and weight files stay ignored.
- **Build check.** `swift build` must pass before you commit. `./build_app.sh` produces
  the runnable app bundle.

## Scope note

NISE (Neural Iterative Selection–Expansion) is deliberately **out of scope** for this
app for now. It is still experimental and lives in NanoHunter. Do not wire it in
without being asked.
