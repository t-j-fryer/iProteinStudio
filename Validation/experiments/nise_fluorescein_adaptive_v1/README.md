# Fluorescein NISE adaptive-sampling retrospective

Read-only analysis of the original `NanoHunter/output/nise_fluorescein` campaign,
not the v2 campaign. No neural inference, new designs, GPU use or timing benchmark.
The input remains immutable. The requested Studio 1,000/30/4 defaults are user
choices, not settings validated by this retrospective.

From the Studio repository, using a Python environment containing NumPy and
Matplotlib (the installed RFdiffusion3 environment was used):

```bash
MPLCONFIGDIR=/private/tmp/nise-fluorescein-retrospective-mpl \
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Validation/experiments/nise_fluorescein_adaptive_v1/analyse.py \
  --source /Users/thomasfryer/NanoHunter/output/nise_fluorescein \
  --output Validation/output/nise_fluorescein_adaptive_v1/analysis
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Validation/experiments/nise_fluorescein_adaptive_v1/report.py \
  --output Validation/output/nise_fluorescein_adaptive_v1/analysis
```

Use a fresh output path for replay: the extractor refuses an existing directory.
`report.py` regenerates derived reports only. The final canonical outputs are in
`output/nise_fluorescein_adaptive_v1/analysis/`. Earlier root-level plots are retained;
the final plot layout fixes a clipped legend without changing the extracted data.

`config.json` declares counts, geometry, proposal levels, threshold comparisons,
2,000 permutations per complete cycle and RNG seed 20260916. `manifest.json`
fingerprints all 21,807 source files read and snapshots saved configuration,
analysis code, Studio HEAD, hardware and explicit provenance limitations.
`audit.json` confirms sequence, geometry, actual-parent coordinate and checksum
checks. The 5,440 raw predictions comprise 85 trajectory-cycles of 64 proposals.
53 missing affinities remain missing; all six affected cycle-five groups are
excluded from subset simulations. Fifteen historical passing CSV rows had used
a pLDDT-only fallback; they are not valid combined scores here.

The simulated policies reuse historical proposals and parents. They cannot predict
future descendants after changing an advanced parent. Fixed-16/32 controls and
16→32→64 / 32→64 alternatives quantify conditional sampling loss, not full-campaign
winner retention or elapsed-time savings. This was beam one, one ligand, Boltz;
beam three, NESSO and RFdiffusion3 require prospective validation. Empty MSAs are
verified in the saved YAMLs; original engine/checkpoint fingerprints cannot be
recovered from the overwritten configuration and are explicitly unknown.

See [Validation entry 0025](../../lab_book/0025-fluorescein-nise-adaptive-retrospective.md)
and [project entry 0135](../../../lab_book/0135-fluorescein-nise-adaptive-retrospective.md).
