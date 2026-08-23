---
entry: 0036
title: Add conservative ipSAE(min) scoring from real PAE outputs
date: 2026-08-23
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ipsae, pae, boltz, intellifold, protenix, prediction, binder-design]
---

## Context

Studio's result model and UI already knew the label `ipSAE(min)`, but no active
predictor calculated it. The completed-results view therefore correctly said it
was absent instead of mislabelling minimum interface PAE or Boltz interface PDE.
The requested metric was the conservative smaller directional ipSAE for protein
multimers and binder predictions, including Protenix. Protenix had been launched
with `--need_atom_confidence False`, so its token-pair PAE and token chain IDs
were not written to disk. This follows the honest metric-display contract in
[[0018-browse-run-results-in-app]] and the strict Protenix policy in
[[0035-fail-loud-msa-and-mps-policy]].

## What was done

- Added one self-contained scorer in `scripts/ipsae_score.py`, numerically
  adapted from DunbrackLab/IPSAE version 4, commit
  `6174cf9e71cb1bd660cc805856a18c4871a6dec3` under its MIT license. Added the
  required notice to `THIRD_PARTY_NOTICES.md`. Studio has no runtime network or
  repository dependency on that project.
- Kept the reference d0res calculation and 10 Å PAE cutoff. Every directional
  chain score is retained. For each unordered chain pair, Studio records the
  smaller directional value; scalar `ipsae_min` is the minimum of those pair
  values when a complex contains more than two protein chains.
- Added fail-loud PAE adapters for Boltz NPZ output, IntelliFold detailed
  confidence JSON and Protenix full-confidence JSON. No score is fabricated for
  OpenFold-3: its detailed output is PDE, not PAE.
- Made Protenix request `--need_atom_confidence True`, verify the exact expected
  full-confidence file count, calculate ipSAE, and copy the annotated best
  summary into its normalised output.
- Routed Boltz scoring through plain Predict, iterative single/cycle-wave runs,
  and RFdiffusion3 verification. IntelliFold and Protenix annotate inside their
  shared launchers, so all workflows inherit the same behavior.
- Added per-engine, mean and minimum ipSAE(min) fields to RFdiffusion3 protein
  design outputs. Existing mean-iPTM ranking remains unchanged; adding a metric
  did not silently alter the established selection policy.
- Made completed predictions/designs and the live iterative design inspector
  show ipSAE(min). Detailed directional and pairwise values remain in the saved
  confidence JSON for auditability.
- Added synthetic equation, engine-format, fail-loud Protenix and cross-engine
  design aggregation regressions, plus a Swift saved-result display regression.

## Results

All checks below ran on the machine in the header. The existing saved Boltz
complex was used only for arithmetic validation; no new model inference was
needed.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Synthetic asymmetric 2 × 2 interface | 2 directions | A→B / B→A | 0.500000 / 0.058824 |
| Same fixture | 1 pair | Studio ipSAE(min) | 0.058824 |
| Saved Boltz nanobody–target complex | 2 directions | Studio A→B / B→A | 0.011325728 / 0.013003819 |
| Same saved Boltz output versus the six-decimal reference rows | 2 directions | absolute difference | 0.000000272 / 0.000000181 |
| Python workflow/format contract | 1 suite | result | pass |
| Ligand conditioning contract | 1 suite | result | pass |
| Iterative CLI contract | 1 suite | result | pass |
| Swift iterative/request/result contracts | 3 executables | passing | 3/3 |
| Full debug Swift build | 1 build | result | pass in 32.65 s |

The local result browser recovered `ipSAE(min) = 0.55` from a saved confidence
fixture. The RFdiffusion3 score fixture retained Boltz 0.60 and IntelliFold 0.40,
reported mean 0.50 and minimum 0.40, while preserving its mean-iPTM score of
0.70.

## Decision and rationale

`ipSAE(min)` means the smaller of A→B and B→A, not the official script's
symmetric maximum row. This is intentionally conservative and matches the
requested product metric. Directional asymmetry is not discarded: every value
is stored under `ipsae_directional`, with pair summaries under `ipsae_pairs`.

The score is calculated only from a predictor's PAE and its exact token-to-chain
mapping. Minimum PAE is not ipSAE, and PDE estimates pairwise distance error
rather than aligned error. Therefore OpenFold-3 remains without this metric
until it emits PAE. Missing PAE for an otherwise applicable multimer is a failed
output contract, not a warning followed by a weaker substitute.

Protenix already computes token-pair PAE for its confidence summaries; its flag
controls whether the detailed arrays and token metadata are dumped. Enabling
the flag is the upstream-supported way to make the calculation reproducible.
The detailed file is retained rather than deleted after scoring because it is
the evidence from which the saved scalar was derived.

The existing iPTM hit threshold and RFdiffusion3 mean-iPTM rank were not changed.
ipSAE(min) is now visible and exportable evidence, but changing campaign
selection requires a separate multi-target validation rather than an
unmeasured assumption that one metric should replace another.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-ipsae-pyc \
  /usr/bin/caffeinate -dimsu \
  /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py

/usr/bin/caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-ipsae-build-clang \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-ipsae-build-swiftpm \
  /usr/bin/caffeinate -dimsu swift build --disable-sandbox \
  --scratch-path /private/tmp/iproteinstudio-ipsae-swift-build
```

The production-file Swift harness commands remain those in
[[0029-retire-untrusted-jax-metal-predictors]].

## Limits and what was not tested

- No new GPU fold was launched after the product owner asked for a code check
  and merge. Protenix full-confidence integration was tested with its exact
  emitted schema and file naming using fixtures, not a new v2/Mini inference.
- Enabling Protenix full-confidence output increases JSON size and serialization
  work. Neither disk growth nor time overhead was benchmarked, so no performance
  claim is made.
- Protein-only multimers and protein chains followed by a ligand are mapped for
  Boltz. A protein placed after a ligand fails loudly because ligand token count
  cannot be inferred reproducibly from YAML alone.
- For complexes with more than two proteins, the scalar is the weakest pair;
  intentionally non-contacting pairs can therefore drive it to zero. Pairwise
  values in the JSON should be used when only selected interfaces are relevant.
- The unrelated verified-downloader test could not bind its loopback test socket
  inside this filesystem sandbox. It was not changed by this work. Ligand,
  workflow, iterative and Swift contracts passed.
- No VoiceOver or large-text pass was performed on the extra live-dashboard
  metric line.

## Next

On the next ordinary Protenix multimer prediction, record full-confidence file
size and annotation time for both Mini and v2. Before promoting ipSAE(min) from a
diagnostic to a design gate or rank term, validate it across multiple known
binders and non-binders rather than one campaign.
