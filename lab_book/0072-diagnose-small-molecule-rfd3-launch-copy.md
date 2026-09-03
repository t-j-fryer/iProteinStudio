---
entry: 0072
title: Diagnose the small-molecule RFdiffusion3 launch copy failure
date: 2026-09-02
author: gpt-5.6-sol
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, gui, small-molecule, launch, diagnostics]
---

## Context

> **Later resolution:** Entry
> [[0073-audit-executable-workflows-across-modalities]] implements the repair,
> discovers and fixes two deeper fixture/conformer collisions, and exercises a
> real installed ligand RFD3→LASErMPNN boundary.

GUI campaign `rfd3-20260902-220705` stopped immediately after preparing a
fluorescein small-molecule design. This was reported after Entry
[[0071-make-agent-rfd3-guidance-fail-safe]], so the first question was whether
the new protein-contig derivation had regressed the GUI.

## What was done

Inspected the saved Studio request, prepared campaign, generated design YAML,
ligand manifest and complete detached-run stdout. Compared the GUI preparation
contract with the installed and source copies of
`run_rfd3_nise_campaign.py`, then checked source history and the prior completed
protein motif campaign.

## Results

no measurements — diagnosis only

The campaign never entered RFdiffusion3. The small-molecule runner raised:

```text
shutil.SameFileError: .../config/design.yaml and .../config/design.yaml are the same file
```

Studio preparation deliberately writes `design.yaml` and `ligand.smi` directly
into the durable campaign `config/` directory and records those exact paths in
`campaign.json`. The small-molecule runner then unconditionally copies both
files to those same destinations. The first copy raises; if skipped, the SMILES
copy would have the same problem.

The protein partial/motif path uses `rfd3_protein_campaign.py` and does not
contain this copy step, which is why the completed p53–MDM2 motif example did
not expose it. Existing contract tests covered preparation and stage functions,
not the small-molecule runner's `main()` with the GUI's in-place paths.

## Decision and rationale

Classify this as a latent small-molecule runner/GUI integration defect, not an
RFdiffusion model, macOS, ligand-conditioning or protein-contig failure. The
safe implementation repair is to copy each provenance input only when source
and destination resolve to different files, while leaving an already in-place
durable config untouched. That repair was not made in this diagnostic-only
entry.

## Reproduce

```bash
tail -240 /Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3_runs/rfd3-20260902-220705/campaign.stdout.log
python3 -m json.tool /Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3_runs/rfd3-20260902-220705/config/campaign.json
```

## Limits and what was not tested

- No source repair or campaign retry was performed.
- No RFdiffusion fixture, backbone, MPNN or predictor stage ran in the failed
  campaign.
- The diagnosis does not establish whether an older direct-RFD3 workflow used
  an external source-config path and thereby avoided the latent defect.

## Next

Add a same-file-safe provenance-copy helper, cover both `design_yaml` and
`smiles_file`, add a runner-entry integration regression, stage the overlay and
resume this exact campaign.
