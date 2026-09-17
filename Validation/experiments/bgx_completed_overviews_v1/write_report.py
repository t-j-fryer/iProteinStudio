"""Document the generated retrospective figures and their numerical units."""
import csv
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'Validation/output/bgx_completed_overviews_v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
timing=list(csv.DictReader((OUT/'timing.csv').open()))
nano=list(csv.DictReader((OUT/'nanobody_pooled_timing.csv').open()))
lengths={(r['engine'],r['condition']):float(r['mean_binder_length_aa'])
         for r in csv.DictReader((OUT/'minibinder_campaign_lengths.csv').open())}
lines=['# Completed Bgx overview figures','','Two retrospective figures matching the requested v7 overview style. No model inference was launched.','',
'- [Minibinders — SVG](01_minibinders_overview.svg) · [PDF](01_minibinders_overview.pdf) · [PNG](01_minibinders_overview.png)',
'- [Nanobodies — SVG](02_nanobodies_overview.svg) · [PDF](02_nanobodies_overview.pdf) · [PNG](02_nanobodies_overview.png)',
'- [Combined PDF](OVERVIEWS.pdf) · [Gallery](GALLERY.html)','','## Statistical units and audit','',
'All 70 campaigns completed. The coordinate audit covers all 5,250 optimized run/cycle structures: 3,500 minibinder and 1,750 nanobody structures. There are 1,050 trajectories. Cycle 00 is excluded from plotted structural/confidence endpoints.', '',
'Dots represent the mean over five cycles within each trajectory. Diamonds represent condition means. Intervals are 95% percentile bootstrap intervals from 10,000 trajectory-level resamples (fixed seed 907026). Minibinder n=50 per engine/condition; nanobody n=7 for Vobarilizumab and Caplacizumab and n=6 for each other scaffold. Cycles are not treated as independent replicates.', '',
'Binder confidence is the arithmetic mean of chain-A Cα pLDDT; it is not complex-average pLDDT or CDR-only confidence. Minibinder secondary structure is Biotite P-SEA on predicted binder coordinates. Nanobody secondary structure was intentionally omitted. All structures passed finite-coordinate, chain identity and sequence checks; normalized and summary-referenced structure bytes matched, normalized iPTM agreed with summaries, and every expected run/cycle existed.', '',
'## Timing definition','',
'Each campaign contributes its latest recorded trajectory end minus its earliest recorded start. Overlapping resident/cycle-wave timers count once. Divide by the number of optimized outputs: 250 per minibinder engine/condition. For nanobodies, sum all eight scaffold campaign spans and divide by 250 outputs per engine. This is a pooled, output-weighted average, accounting for six versus seven trajectories per scaffold.', '',
'Initialization and MPNN are included; queue/setup before the first trajectory timer and gaps between separate scaffold campaigns are excluded. Pauses inside a recorded campaign span remain included. No timing CI is assigned to these aggregates. Historical machine attribution: Apple M4 Max, 64 GB, as recorded by this project for these local campaigns; hardware was not rebenchmarked. Times below are calculated from the original timing_run.csv records, not new inference measurements.', '',
'Timing-bar labels include the actual mean binder length across 50 trajectories per campaign. Length is constant across the five optimized cycles within every trajectory; the trajectory-weighted and optimized-output-weighted means therefore agree. These labels provide size context; timing is not normalized per residue.', '',
'| Engine | Minibinders h0, s/design | h0 mean length, aa | Minibinders h1, s/design | h1 mean length, aa | Nanobodies pooled, s/design |','|---|---:|---:|---:|---:|---:|']
for row in nano:
 e=row['engine']; vals={r['condition']:float(r['seconds_per_design']) for r in timing if r['kind']=='minibinder' and r['engine']==e}
 lines.append(f"| {e} | {vals['0']:.1f} | {lengths[e,'0']:.2f} | {vals['1']:.1f} | {lengths[e,'1']:.2f} | {float(row['seconds_per_design']):.1f} |")
lines += ['', '## Interpretation and limits','',
'Minibinder h0 uses 65–150 residues; h1 uses 65–120 residues, and the recorded seeds differ. These are not matched intervention arms. Nanobody lengths range from 115 to 128 residues; timing is pooled as requested. Engine settings, confidence calibration and scheduling differ; figures show descriptive results, not controlled speed or accuracy rankings. The dashed iPTM line is the saved 0.7 threshold, not experimental binding evidence. No independent post-design checks or wet-lab binding validation are inferred.', '',
'Inputs and original frozen launch helpers were read without modification. source_sha256.json records raw source hashes; campaign_provenance.json retains original requests, command arguments, scheduler settings, target-MSA hashes and frozen runner hashes. Historical weights are not retrospectively assigned new run-time hashes: this analysis does not prove equivalence of model installations across engines. Full neural inference and geometry-violation reclassification were not rerun.', '',
'## Reproduce','',
'Use Validation/experiments/bgx_completed_overviews_v1/README.md. The full analyse.py command re-audits source data; --plot-only redraws cached trajectory means. Run write_report.py after rendering to refresh this report and artifact hashes. Figure-only layout revisions may have a different rendering-source hash from the preserved extraction source.', '',
'## Files','',
'- structures.csv: all 5,250 audited optimized cycle measurements.',
'- trajectories.csv: 1,050 five-cycle means.',
'- summary.json: plotted means, bootstrap intervals and group sizes.',
'- timing.csv: 70 recorded campaign spans and per-output costs.',
'- minibinder_campaign_lengths.csv: actual mean lengths for all 14 minibinder campaigns.',
'- nanobody_pooled_timing.csv: seven requested pooled engine costs.',
'- integrity.json, source_sha256.json, campaign_provenance.json: audit/provenance.',
'- artifact_sha256.json: checksums of generated deliverables.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
integrity=json.loads((OUT/'integrity.json').read_text())
integrity.update(rendering_source_sha256=sha(HERE/'analyse.py'),report_source_sha256=sha(Path(__file__)),manifest_sha256=sha(HERE/'manifest.json'))
if (OUT/'extraction_source.py').exists():integrity['extraction_source_sha256']=sha(OUT/'extraction_source.py')
(OUT/'integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
(OUT/'artifact_sha256.json').write_text(json.dumps({p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='artifact_sha256.json'},indent=2)+'\n')
