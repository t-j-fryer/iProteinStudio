---
entry: 0010
title: A fresh install was missing the entire RFdiffusion3 script layer
date: 2026-08-13
author: claude-opus-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [install, reproducibility, rfd3, updates]
---

## Context

Asked to make everything reproducible and installable for a fresh user, and to
say whether people who have already installed will get updates. Checking the
first question turned up a defect that made the RFdiffusion3 tab unusable for
anyone but this machine.

## Results

### The installer produced an RFdiffusion3 that could not run anything

`setup_pipeline.sh --with-rfd3` clones `javierbq/rfd3-mlx`. That clone contains
**none** of the scripts Studio drives:

```
$ git clone --depth 1 https://github.com/javierbq/rfd3-mlx.git fresh/rfd3
$ ls fresh/rfd3/scripts/*.py | wc -l
0
```

Twenty-seven scripts — `design_from_yaml.py`, `run_rfd3_nise_campaign.py`,
`run_predictors.py`, `prepare_ligand_target.py`, `build_length_bins.py`, the three
predictor adapters, all of it — plus `milestone0_oracle.py`, are work layered on
top of that port. On this machine they exist because they were written here. On a
new machine they would simply be absent, and every RFdiffusion3 feature would
fail at the first subprocess call.

This had been invisible for the same reason as the shebang bug in
[[0008-self-contained-install-and-remaining-backends]]: the development machine
was never installing, it was linking to a checkout that already had everything.

### The fix

`tools/sync_rfd3.sh` vendors the whole layer into
`Resources/rfd3_overlay/` (340 KB), and it is applied over the checkout
**immediately after cloning** — which has to be that order, because
`install_rfd3.sh` itself calls `scripts/patch_foundry_rasa.py` and
`scripts/prepare_fluorescein.py`, so a clean clone cannot even install without
the overlay first.

| | Before overlay | After |
|---|---:|---:|
| Scripts in a clean clone | 0 | 27 |
| `milestone0_oracle.py` | absent | present |
| All vendored scripts compile | — | 28 / 28 |
| App bundle size | 14 MB | 14 MB |

Applied by merge rather than replace, so campaign outputs and cached fixtures in
an existing checkout survive.

### Updates: what does and does not reach an existing installation

The same staging is the update mechanism, and the honest answer has three parts.

**Scripts update.** Everything shipped in the bundle — pipeline, Studio helpers,
RFdiffusion3 overlay — is re-staged on launch. The overlay is version-stamped by
a checksum over its contents, so it is rewritten only when the bundle differs
from what is installed. Verified: matching stamps mean no copy.

**Environments and weights do not.** Python environments and multi-gigabyte model
weights are untouched by an update. That is deliberate — re-downloading them on
every launch would be indefensible — but it means a change that needs a new
dependency or model is a *setup* step, not an update, and has to say so.

**The app does not update itself.** There is no updater and no signing. A new
build is something someone has to run.

### Two smaller corrections

- **IntelliFold now says which build it is.** "IntelliFold" and "IntelliFold
  (JAX)" gave no way to tell them apart; they are now "IntelliFold (PyTorch)" and
  "IntelliFold (JAX/MPS)", with the trade-off — 1.24× faster, about twice the
  memory, slightly different numbers — in the description rather than implied.
- **The prediction tab's engine list is written out explicitly** rather than
  derived by filtering another list. OpenFold-3 was in fact present, but a list
  built by subtraction is one edit away from silently losing an engine, and there
  is no reason for that list to be computed.

## Decision and rationale

**Vendor the whole script layer, not a patch set.** A patch against upstream
would need upstream to have the files being patched, and it does not have any of
them. Full copies also mean the app bundle is a complete, inspectable record of
what a user will run.

**Apply before RFdiffusion3's own installer.** Not a nicety — `install_rfd3.sh`
calls overlay scripts, so the reverse order cannot work.

**Merge, don't replace.** An installed checkout accumulates campaign outputs and
cached fixtures. Replacing directories wholesale would delete a user's results to
deliver a script update.

**Version-stamp by content checksum, not by date.** A timestamp changes when the
file is copied; a checksum changes when the content does. Only the second is a
reason to rewrite anything.

## Reproduce

```bash
# The defect
git clone --depth 1 https://github.com/javierbq/rfd3-mlx.git /tmp/fresh_rfd3
ls /tmp/fresh_rfd3/scripts/*.py | wc -l          # 0

# Re-vendor and check the bundle
./tools/sync_rfd3.sh /Users/thomasfryer/RFD3
./build_app.sh
ls "build/NanoHunter Studio.app/Contents/Resources/"*.bundle/rfd3_overlay/scripts/*.py | wc -l
```

## Limits and what was not tested

- **A true from-scratch install has still never been run.** This entry proves the
  overlay makes a clean clone complete; it does not prove that
  `setup_pipeline.sh` succeeds end to end on an empty machine. That has now been
  the top open item for two entries and remains the single biggest risk to the
  claim of reproducibility.
- The overlay was applied to a clean clone by hand, mirroring what the installer
  does. The installer's own overlay step has not executed.
- Nothing was folded after applying the overlay to a clean clone — the scripts
  are present and parse, which is not the same as working.
- `milestone0_oracle.py` is vendored because everything depends on it. Its
  provenance relative to the unlicensed upstream port has not been established,
  and the repo is private partly for that reason
  ([[0001-repository-genesis-and-audit]]).
- The update path is verified only in the matching-stamp direction (no copy when
  identical). A genuine bundle-newer-than-installed update has not been observed.

## Next

1. Run `setup_pipeline.sh` into an empty root on a machine with nothing
   installed. Everything else about reproducibility is downstream of it.
2. Fold something through a clean-clone RFdiffusion3 to confirm the overlay is
   sufficient and not merely complete.
3. Studio still has no measurements of its own. Six entries running.
