# 0195 — Biotin affinity and CPU efficiency qualification

2026-10-15. In progress. Protocol, scope and execution evidence:
[project0432](../../lab_book/0432-run-biotin-affinity-efficiency.md).

48saved designs from two completed biotin NISE runs;200/5 vs50/1 affinity,
two distinct paired seeds plus an eight-case same-seed control. Four-case smoke
before main replay. Exact original full-precision saved inputs and empty MSA;
five affinity recycles/ensemble unchanged. Bound CPU geometry1/2/4/8 processes;
serial vs overlapping independent LASErMPNN/geometry/affinity workload.
Hardware M4Max40GPU/64GB. Source commit recorded in host.json; exact runtime,
script, checkpoint and input hashes in immutable managed plan. No production
promotion. Four CPU contract tests and48-case input audit passed; real compute
pending. Output `output/biotin_affinity_efficiency_v1/20261015T234303Z`.

An earlier preparation attempt retained at20261015T234045Z stopped while reading
host sysctl inside the sandbox; no job submitted or inference run from that attempt.

Managed plan8b436ddca9bc3670, SHA2568b436ddca9bc3670c2f2b98600431ee38314f1bc8bbd6db048552829d1838a3d; job-8b436ddca9bc submitted2026-10-15T23:43:53Z. Source cohort input audit passed. Predecessor job-cae46f604ea5 was immediately cancelled before inference to correct geometry settings extraction: these fields live in nise_config.json.request, not the upstream config.json. Its immutable directory remains preserved at20261015T234105Z.

User curtailed second seeded repeat2026-10-15T20:09EDT. job-8b436ddca9bc cancelled through broker; all48 first-seed pairs complete and audited. Paired mean21.631s vs5.654s/design (3.82565x); P(bind) MAE.0105849,max.033429,Spearman.997612. Combined top10 unchanged; pooled P(bind)-only top10 retains9/10. One early0.80 gate crossing (.808854 to.787324). Four same-seed smoke/main controls match exactly under both settings. See analysis/FIRST_SEED_REPORT.md and first_seed_summary.json. Shortened CPU follow-up atValidation/output/biotin_affinity_efficiency_v1/cpu_followup_20261016T000959Z: no second affinity-seed cohort, one same-seed serial/overlap pair plus warmup (18light calls). Geometry sweep separate from cycling.

CPU follow-up completed: job-f4db470073e8, output cpu_followup_20261016T001422Z.
Geometry exact at1/2/4/8workers, two orders. Eight-worker0.940–0.951s vs
one-worker2.716–2.727s over48structures. One serial/overlap pair53.7434/48.1476s,
all CPU outputs and eight affinity outputs identical. Original second-seed trial
remains cancelled. See0196/0433 for path-bug repair and subsequent managed queue.
