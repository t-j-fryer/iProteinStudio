# 0201 — Qualify shipping ligand efficiency

2026-10-16. Status: completed; numerical equivalence qualified with limits below.

Experiment: experiments/product_efficiency_release_v1/manifest.json.
Four saved biotin starts (two Boltz/two RFD3), two complete refinement cycles,
paired fresh-process CPU sampling versus resident/bounded-prefetch CPU sampling.
Both arms use two CPU slots; the fresh arm holds a barrier before folding. Both
arms use identical upstream LASErMPNN parameters/seeds and resident Boltz structure
3/25 plus affinity50/1, native affinity5recycles/twoheads, no MSA/pocket, potentials
on. Check sequences, structure hashes, affinity/ligandconfidence and geometry,
then replay durable operations. Hardware: M4Max40GPU/64GB. Outputs and immutable
code/runtime/input fingerprints belong to the broker plan and its output folder.

Reduced affinity scientific-budget evidence is the separate 48-case experiment
0195/0432; this test checks integration, not universal ligand accuracy. No raw
outputs edited. No default performance number extrapolated from CPU-only work.

The bounded follow-up runs64 resident requests (128 sequences), compares each
with a fresh seeded call, records worker RSS, interrupts only its own CPU worker
and checks fresh-worker recovery. Declared late-growth bound128MiB after16calls.
These are short qualification runs, not a multi-day memory guarantee.

Completed: paired exact check failed on tiny coordinate/confidence differences;
separate numerical audit passes with all sequences, P(bind), geometry and rankings
identical. CPU64-call soak and interrupted-worker recovery pass. Full measurements,
limits and the preserved exact failure are in project0442 and its artifacts.
