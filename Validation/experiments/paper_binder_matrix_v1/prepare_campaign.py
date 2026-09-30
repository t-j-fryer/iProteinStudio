"""Freeze the full campaign only after manually reviewed benchmark selection."""
import json,sys,os,shutil,time,subprocess
START=time.perf_counter()
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];root=Path.home()/'.iproteinstudio'
base=REPO/'Validation/output/paper_binder_matrix_v1';cfg=json.loads((base/'inventory.json').read_text())
selection_path=Path(sys.argv[1]);selection=json.loads(selection_path.read_text())
assert set(selection['variants'])==set(cfg['engines'])
assert selection['reviewed'] is True
assert all(Path(r['design_name']).name==r['design_name'] and r['design_name'] not in ('.','..') for r in cfg['rows'])
assert len({r['design_name'].replace('_','-') for r in cfg['rows']})==len(cfg['rows'])
out=base/'campaign';out.mkdir(exist_ok=False);frozen=out/'frozen';frozen.mkdir()
for p in HERE.glob('*.py'):shutil.copy2(p,frozen/p.name)
for name in ('ipsae_score.py','storage_policy.py'):
 shutil.copy2(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'/name,frozen/name)
shutil.copy2(HERE.parent/'sumo_model_matrix_exact_v1/quality.py',frozen/'quality.py')
reference=json.loads((REPO/'Validation/output/sumo_model_matrix_exact_v1/inputs/reference.json').read_text())
reference['sequence']=cfg['sequence']
(frozen/'reference.json').write_text(json.dumps(reference,indent=2)+'\n')
shutil.copy2(selection_path,frozen/'selection.json')
ordered=sorted(cfg['rows'],key=lambda r:(r['target_key'],len(r['binder_sequence']),r['design_name']))
seen=set();smokes=[]
# Stress the longest complex for each target before the bulk, then group by size.
for row in sorted(ordered,key=lambda r:(r['target_key'],-len(r['binder_sequence']),r['design_name'])):
 if row['target_key'] not in seen:smokes.append(row);seen.add(row['target_key'])
smoke_names={r['design_name'] for r in smokes}
cfg.update(phase='campaign',output=str(out),seeds=selection['seeds'],arms=list(selection['variants'].items()),selected_rows=smokes+[r for r in ordered if r['design_name'] not in smoke_names],smoke_names=sorted(smoke_names),selection=selection)
cfg.update(normal_predictions=len(cfg['selected_rows'])*len(cfg['arms'])*len(cfg['seeds']),diagnostic_replays=0)
cfg.pop('reuse_engine_outputs',None)
assert len(cfg['selected_rows'])==674 and len(smokes)==7
cfg['timing']='Synchronized GPU stage timing every prediction; CPU preparation, native serialization/writing and independent audit recorded separately. Nested stage times are not additive.'
cfg['scheduler']='Each engine loads once; first complete one audited prediction for each of seven distinct targets, then all remaining binders grouped by target and length. Per-unit hash checkpoint, bounded caches, serial shared GPU lease.'
cfg['esm_native_schedule_note']='Pinned native ESM sampler truncates its schedule: Full requested13 runs10 denoising iterations; Fast requested50 runs34. Same native behavior as prior SUMO matrix.'
from assets import fingerprint
print('Fingerprinting external model assets; weights are not copied.',flush=True)
fingerprint_started=time.perf_counter()
cfg['asset_fingerprints']=fingerprint(root,cfg['engines'])
cfg['asset_fingerprint_seconds']=time.perf_counter()-fingerprint_started
(frozen/'asset_fingerprints.json').write_text(json.dumps(cfg['asset_fingerprints'],indent=2)+'\n')
dependencies=subprocess.check_output([cfg['analysis_python'],'-c',
 'import importlib.metadata as m,json,sys; print(json.dumps(dict(python=sys.version,packages={d.metadata["Name"]:d.version for d in m.distributions()}),indent=2))'],text=True)
(frozen/'analysis_dependencies.json').write_text(dependencies)
(frozen/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
from iprotein_mcp.plans import _persist,_script_provenance
python=str(root/'components/control/current/python/bin/python3')
command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','PYTORCH_ENABLE_MPS_FALLBACK=0','OMP_NUM_THREADS=4','VECLIB_MAXIMUM_THREADS=4','MKL_NUM_THREADS=4','KMP_USE_SHM=0','HF_HUB_OFFLINE=1','TRANSFORMERS_OFFLINE=1','TOKENIZERS_PARALLELISM=false','/usr/bin/caffeinate','-dimsu',python,str(frozen/'run.py'),str(frozen/'config.json')]
engines=list(selection['variants'])
normalized=dict(workflow='runtime_benchmark',engines=engines,runtime_python_paths=[cfg['engines'][e]['python'] for e in engines],output=str(out),msa_policy=cfg['protocol'],scheduler=cfg['scheduler'],steps=[dict(stage='paper-predictions',command=command,cwd=str(out))])
files=list(frozen.iterdir())+[Path(t['msa']) for t in cfg['targets'].values()]+[Path(cfg['engines'][e]['python']) for e in engines]
preflight_started=time.perf_counter()
plan=_persist('desktop_runtime_benchmark','paper-binder-matrix',normalized,command,'apple_gpu_exclusive',_script_provenance(files));(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(plan['id'],plan['sha256'])

(out/'preflight_timing.json').write_text(json.dumps(dict(broker_preflight_seconds=time.perf_counter()-preflight_started,total_prepare_seconds=time.perf_counter()-START),indent=2)+'\n')
