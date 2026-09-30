"""Read-only timing aggregation; no inference or changes to raw predictions."""
import json,statistics
from pathlib import Path
from datetime import datetime,timezone

out=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_exact_v1'
data=json.loads((out/'analysis/results.json').read_text())
rows=[r for r in data['rows'] if r['engine']!='openfold3']
rows += [json.loads(p.read_text()) for p in (out/'openfold3_retry03').glob('*/measurement.json')]
summary=[]
for engine in data['loads']:
 arm='none' if engine=='esmfold2_fast' else '128'
 selected=[r for r in rows if r['engine']==engine and r['msa']==arm and r['budget']=='full' and not r['diagnostic'] and not r['first_model_request']]
 if not selected:continue
 median=statistics.median
 model=lambda r:r['stages']['model_total']['seconds']
 summary.append(dict(engine=engine,msa=arm,n=len(selected),seeds=[r['seed'] for r in selected],
  request_seconds=median(r['request_seconds'] for r in selected),
  model_seconds=median(model(r) for r in selected),
  outside_seconds=median(r['request_seconds']-model(r) for r in selected),
  stages={k:median(r['stages'][k]['seconds'] for r in selected if k in r['stages']) for k in selected[0]['stages'] if k!='model_total'}))
payload=dict(updated_at=datetime.now(timezone.utc).isoformat(),hardware='Apple M4 Max, 64 GB (campaign manifest)',rows=summary,
 caveats=['Medians computed independently; difference of medians need not equal median difference.',
 'Model timer covers engine-specific inference functions, not exclusively GPU kernels.',
 'Initial weight loading, input-YAML staging and post-request benchmark geometry audit are outside request timer.',
 'Native workflow output writing/validation inside session.predict is included; cached MSA files, no remote search.',
 'Stage sub-timings do not partition all overhead. Attribution below is code evidence, not measured component speedups.'])
(out/'analysis/request_overhead.json').write_text(json.dumps(payload,indent=2)+'\n')
lines=['# Resident request overhead review','',payload['updated_at'],'',payload['hardware'],
 '', 'Native diffusion budget; 128-row MSA except sequence-only ESMFold2 Fast. Normal warm requests only.',
 '', '| Engine | n | Request median (s) | Inference median (s) | Median outside inference (s) |',
 '|---|---:|---:|---:|---:|']
for r in summary:lines.append(f"| {r['engine']} | {r['n']} | {r['request_seconds']:.3f} | {r['model_seconds']:.3f} | {r['outside_seconds']:.3f} |")
lines+=['','## Interpretation','',*['- '+c for c in payload['caveats']],
 '', 'OpenFold recreates its DataModule for each request; the saved configuration has 10 loader workers. Upstream persistent_workers=True only persists within that loader lifetime. macOS spawn must initialize child interpreters; its cost has not yet been isolated.',
 '', 'Both OpenFold and Boltz invoke Lightning Trainer.predict for every request. Installed Lightning teardown calls lightning_module.cpu(), and setup moves the module to the selected device. The model object/weights survive in the host process, but this does not guarantee continuous MPS residency. Transfer/setup/teardown times remain unmeasured individually.',
 '', 'IntelliFold process_inputs takes about 2.5 s in these conditions and loads ccd_v2.pkl on each invocation. Unpickling is a candidate contributor, not yet individually timed. Cache validated immutable chemical data in a resident session, then measure.',
 '', 'Priorities: (1) OpenFold 0/1/2 versus 10 loader workers with identical feature RNG and output audits; (2) IntelliFold CCD and deterministic parsed-input caching; (3) Boltz/OpenFold continuous device residency using a scoped session lifecycle; (4) CPU prefetch across ready requests with bounded memory and per-record RNG.',
 '', 'Cache only deterministic preparation keyed by sequence, alignment/template/ligand contents, engine version and settings. Preserve seed-dependent conformers, crops and MSA sampling. Keep atomic output/checkpoint and confidence/geometry checks. Validate same-seed features, coordinates and confidence; repeat mixed-length, cancellation/resume and memory checks before promotion.',
 '', 'No optimization is promoted by this review; current matrix remains unchanged.',
 '', 'PyTorch reference: https://docs.pytorch.org/docs/main/data.html']
(out/'REQUEST_OVERHEAD.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(payload,indent=2))
