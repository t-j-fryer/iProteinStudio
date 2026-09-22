# 0048 — MPSGraph scratch recovery (22 September 2026)

Completed on M4 Max64GB/macOS26.6.1. Manifest and machine-readable results: `experiments/mps_scratch_recovery_v1/manifest.json` and `qualification.json`.

The retained previous Boltz environment reproduced the native mkdir stall before repair; its timeout/termination failure was retained. A separately authorized atomic rename preserved the entire affected directory and an empty same-permission replacement restored access. No shared contents were deleted. Why the original directory reached that state remains undetermined.

After repair,12 Boltz predictions across old/published runtimes, four fresh processes and three resident requests each passed. All12 saved CIFs are byte-identical to the original qualified reference; PAE/PDE/scalar confidence scores match exactly. Settings: ubiquitin76, empty MSA, seed42,3 recycles,200 diffusion steps, potentials retained. Two PSICHIC64-case runs passed the0.001 scalar gate and completed-resume audit (GPU ESM batch8/CPU graph scoring). The installed public Boltz workflow also completed1/1 with0 failures and its new storage guard passed.

The product check is bounded, creates/removes only its own empty probe, records a diagnostic and stops before inference if storage fails. Seven focused behavioral tests,18 MCP regression tests,2 snapshot tests and Swift builds pass. No scientific defaults/runtime packages changed. No controlled throughput, fresh-Mac, other-chip or multi-day reliability claim. Project Lab Book0178 records exact jobs, limitations and release verification.

Published0.2.2 build45/MCP23; GitHub asset digests, Sparkle signature/feed, installed resources and preserved previous app verified. Final scratch check passed with238 entries and no active validation jobs. Full receipt is in project0178.
