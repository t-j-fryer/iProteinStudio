---
entry: 0016
title: Complete RFD3 and nanobody campaigns, then make runs recoverable
date: 2026-08-14
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, nanobody, msa, ui, recovery, accessibility]
---

## Context

Entry [[0015-gui-gpu-and-usability-audit]] proved real GPU launches but stopped
the RFdiffusion3 protein acceptance after backbone generation and identified
persistent history, progressive disclosure, actionable errors and a global
activity view as the highest-value product gaps. This pass completed both a
protein RFD3 campaign and a nanobody design job, fixed what the complete path
exposed, and implemented those product changes.

## What was done

- Ran the protein RFD3 path for alpha-cobratoxin through fixture preparation,
  one 65-residue backbone, SolubleMPNN, target-MSA handling, Boltz complex
  prediction and final ranking.
- Fixed `score_and_select.py`: its old schema was ligand-only and required
  `ok`, `ligand_plddt` and `pbind`, so a valid protein predictor row could never
  rank. `--protein --sequences` now requires exit code 0, a structure and iPTM
  from every requested predictor, then ranks by mean iPTM and records minimum
  iPTM. It does not invent ligand scores or silently accept missing predictors.
- Added checkpoint-aware `--resume` and a PID file to the protein campaign
  runner. Reopening Studio can distinguish live from interrupted campaigns,
  and retry skips recorded stages. An exact pre-existing target MSA is reused
  only when its first record equals the requested target and it has at least
  two records; otherwise the stage fails or generates the requested alignment.
- Ran one complete Vobarilizumab (`7xl0`) nanobody job: AntiFold redesigned only
  CDR3, using the bundled scaffold MSA and a required target MSA, and Boltz
  evaluated seed and redesigned complexes on MPS.
- Verified both masked scaffold alignments contained 256 records. All 255
  homologues had scaffold positions 97–110 masked while retaining framework
  signal; the designed sequence changed only positions 97–110.
- Added durable `studio_run.json` manifests and `studio.log` files for new
  iterative runs. The manifest stores the exact arguments plus the small set of
  non-secret scientific environment overrides, so Resume never reconstructs a
  run from settings that may since have changed.
- Moved Prediction and RFD3 output to unique timestamped run directories. A new
  disk-backed history scanner also recognizes legacy output directories and
  classifies completed, failed, live and interrupted work.
- Added a global Activity panel and per-project run history with safe Stop,
  Resume, Reveal and status actions. RFdiffusion3 also reattaches using its PID
  and displays a ranked-result summary when complete.
- Added Quick setup / Advanced disclosure, sticky Start bars, plain-language
  error cards with Retry and Reveal actions, collapsed technical logs, keyboard
  access to Activity, and additional accessibility labels across the forms.
- Changed every Studio-owned iterative, Prediction and RFD3 launch route to
  `caffeinate -dimsu`, so both system and display sleep are inhibited for a job's
  lifetime without relying on the testing shell.

## Results

These are one-run acceptance observations on the machine in the header, not
general performance claims.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| RFD3 MLX, 65-aa binder, 10 steps | 1 | backbone bin wall time | 0.787466 s |
| SolubleMPNN, 1 backbone / 1 sequence | 1 | stage wall time | 2.086782 s |
| Boltz verifier, 136 total protein residues | 1 | stage wall time | 25.374820 s |
| Ranked RFD3 design | 1 | Boltz / mean / minimum iPTM | 0.883970 |
| Nanobody cycle 00, 121-aa binder + 71-aa target | 1 | cycle wall time | 33.581887 s |
| Nanobody cycle 01, same topology | 1 | cycle wall time | 41.516976 s |
| Nanobody cycle 00 | 1 | iPTM | 0.840427 |
| Nanobody cycle 01 | 1 | iPTM | 0.780964 |

The RFD3 verifier and all three nanobody Boltz predictions explicitly logged
`GPU available: True (mps), used: True`. RFD3 produced one backbone, one
SolubleMPNN sequence, one successful predictor row, a complex structure and a
one-row `analysis/top100.csv`. The target alignment used by the RFD3 predictor
contained 1,148 records.

The nanobody run exited 0 and produced both cycle structures, per-cycle metrics
and a final summary. Its bundled scaffold alignment source contained 12,014
validated records; the target alignment contained 1,148. The final sequence was
121 residues and framework positions outside CDR3 were unchanged. The lower
cycle-01 iPTM is not evidence for or against the design method; this run only
tests correctness of the route and artifacts.

## Decision and rationale

**Protein and ligand ranking have separate validity rules.** Reusing a single
table is useful, but treating absent ligand columns as low protein scores is a
silent scientific error. Protein mode now validates the outputs protein models
actually produce and rejects incomplete predictor ensembles.

**Resume from a recorded command, not the current form.** A scientist may edit a
project after a crash. Resuming with today's controls could create a mixed
campaign that is not reproducible. The durable manifest is therefore the source
of truth; old runs remain visible but cannot claim exact Resume without one.

**Keep one run per directory.** Reusing `predictions/` or `rfd3/` overwrote the
user's prior history and made recovery ambiguous. Timestamped roots make the
filesystem itself an audit trail while legacy roots remain readable.

**Inhibit sleep for the process lifetime.** A fixed-duration test wrapper can
expire during a real campaign. Studio now wraps each launched workload itself,
so the assertion ends when the process ends.

## Reproduce

The exact request used for this acceptance run was saved as
`/private/tmp/iproteinstudio-rfd3-complete-request.json`. Its scientific settings
were alpha-cobratoxin chain B residues 1–71; hotspots B67, B69 and B71; a 65-aa
binder; one backbone; 10 steps; one recycle; batch and queue size 1; bf16; one
SolubleMPNN sequence; and Boltz verification.

```bash
cd /Users/thomasfryer/iProteinStudio

/usr/bin/caffeinate -dimsu python3 \
  Sources/iProteinStudio/Resources/rfd3/rfd3_protein_campaign.py \
  --config /private/tmp/iproteinstudio-rfd3-complete-request.json

# Confirm completed stages are skipped rather than repeated.
/usr/bin/caffeinate -dimsu python3 \
  Sources/iProteinStudio/Resources/rfd3/rfd3_protein_campaign.py \
  --config /private/tmp/iproteinstudio-rfd3-complete-request.json \
  --stage score --resume

bash -n Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh
PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-pycache python3 -m py_compile \
  Sources/iProteinStudio/Resources/rfd3/rfd3_protein_campaign.py \
  Sources/iProteinStudio/Resources/rfd3_overlay/scripts/score_and_select.py \
  Sources/iProteinStudio/Resources/rfd3_overlay/scripts/launch_rfd3_nise_campaign.py
swift build
./build_app.sh
```

The nanobody job used `/private/tmp/iproteinstudio-nanobody-template.yaml`, the
managed `nanohunter_run.sh`, workflow `protein`, predictor `boltz`, designer
`antifold`, scaffold `7xl0_vobarilizumab`, CDR3 only, one run, one optimisation
cycle, required automatic target MSA and no post predictor. Its output root was
`/private/tmp/iproteinstudio-nanobody-20260814`.

## Limits and what was not tested

- The first full RFD3 attempt reached ranking and exposed the ligand-schema bug;
  the fixed score stage was resumed from the existing verified artifacts. The
  whole six-stage route was therefore accepted as a checkpointed campaign, not
  repeated as one uninterrupted run.
- The initial full RFD3 job used a pre-seeded copy of the shipped
  alpha-cobratoxin alignment. A separate fresh `msa`-stage run confirmed the
  new exact-sequence cache lookup automatically found and validated it.
- Both heavy jobs used the exact production entry points invoked by the GUI,
  but were launched from the command line to keep acceptance settings isolated
  from the user's saved project. A full heavy campaign was not started by a GUI
  button in this pass.
- No small-molecule RFD3/NISE campaign, extra RFD3 verifier ensemble, post-design
  predictor or non-Vobarilizumab scaffold was repeated.
- Exact iterative Resume is implemented and source/build checked, but no new
  multi-hour GUI job was deliberately interrupted and resumed. Legacy recovery
  and result states were inspected in the release GUI.
- Accessibility was inspected through macOS Accessibility APIs and screenshots;
  it was not a complete external-user VoiceOver, keyboard-focus, large-text,
  reduced-motion or contrast study.
- No cold install on a second Mac, signing, notarisation, updater, or AlphaFold 3
  parameter redistribution was attempted.

## Next

1. Exercise exact-manifest Resume by interrupting a small GUI campaign after a
   completed checkpoint, relaunching the app, and resuming from Activity.
2. Add a richer structure/ranking browser for RFD3 beyond the current summary
   and Reveal action.
3. Complete an external accessibility pass, then address signing, an app icon
   and update delivery.
