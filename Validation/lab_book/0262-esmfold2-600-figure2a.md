# 0262 — ESMFold2-600 Figure 2a benchmark

Date: 2026-10-26. Status: complete. Project Lab Book 0582.

Declared protocol and executable code: `experiments/esmfold2_600_figure2a_v1/`.
Four original Figure 2a constructs/masks; warmup then seeds 42–46 per resident block.
Primary4 GiB-cache/unchunked and separate 512 MiB-cache/chunk32 arms;40 measurements,
8 warmups. Exact current model/runtime identities are retained by the managed plan.
Original Figure 2a profiling, memory and accuracy helpers are copied unchanged with
source hashes. Dimer support is research-only. No16 GB hardware, independent cold
replicates, biological validation, universal throughput or default promotion.

Results, failures, output audit and queue restoration will be recorded after completion.

Corrected job`job-e0bb25378343` completed40 measured outputs and8 warmups.
All 288 receipt-listed files verified; host timing gate passed (243 samples, no
compilers, no sustained external CPU event). First attempt was cancelled because
an environment assignment bypassed the frozen runtime view; it is retained and
excluded. Corrected per-block runtime-view assertions passed. Full numbers and
limits are in project0582; CSV/JSON/report under
`output/esmfold2_600_figure2a_v1_retry2/analysis/`. No defaults or figures promoted.

Final Swift build/bridge checks passed. Original campaign running and follow-on
job queued again with unchanged plan digests; receipts retained in the delivery
folder. Intended source changes mirrored to the canonical repository.
