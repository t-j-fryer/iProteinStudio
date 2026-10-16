# LASErMPNN CPU residency qualification

Four saved, already prepared biotin complexes (two from each generator), one and
five samples per request; two alternating repeats of fresh processes and resident
pools of one/two/four workers with one thread, plus two workers with two threads.
240 total sequences. Use the unchanged upstream run_inference path, cache only
model loading, and reset Python/NumPy/Torch RNG after loading. Compare complete
FASTA bytes including scores. This is a new explicit test seed policy; historical
NISE's ignored LASErMPNN seed is not reproducible retroactively.

`prepare.py --start` freezes inputs, settings, scripts and weight fingerprints and
starts through Studio's immutable plan and shared execution lease. No weight copy,
upstream package patch, production default change or new backbone generation.

Timing includes model import/loading and pool teardown. Request times and peak
per-worker RSS are also saved. Four inputs/two repetitions do not qualify a long
memory soak, interrupted-job resume or CPU/GPU overlap. Prepared inputs exclude
protonation and initial file conversion; those are separate profiling targets.
