"""Declare/freeze an isolated screen and preserve its immutable broker plan."""
import json,sys,os,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
root=Path.home()/'.iproteinstudio'
cfg=json.loads((REPO/'Validation/output/paper_binder_matrix_v1/inventory.json').read_text())
phase=sys.argv[1] if len(sys.argv)>1 else 'benchmark'
out=Path(cfg['output'])/phase;out.mkdir(exist_ok=False);frozen=out/'frozen';frozen.mkdir()
for p in HERE.glob('*.py'):shutil.copy2(p,frozen/p.name)
cfg.update(phase=phase,output=str(out))
candidates=sorted([r for r in cfg['rows'] if r['target']=='SUMO'],key=lambda r:(len(r['binder_sequence']),r['design_name']))
cfg['selected_rows']=[candidates[round(i*(len(candidates)-1)/4)] for i in range(5)]
cfg['arms']=[['boltz','baseline'],['boltz','resident'],['boltz','reuse'],['boltz','metal'],['intellifold_flash','baseline'],['intellifold_flash','resident'],['intellifold_flash','inference'],['intellifold_flash','metal'],['openfold3','baseline'],['openfold3','resident'],['openfold3','reuse'],['esmfold2_fast','baseline'],['esmfold2_fast','chain'],['esmfold2_full','baseline'],['esmfold2_full','chain'],['protenix_v2','baseline'],['protenix_v2','inference'],['protenix_v2','metal'],['protenix_mini','baseline'],['protenix_mini','inference'],['protenix_constraint','baseline'],['protenix_constraint','inference']]
if phase=='positions':cfg['arms']=[['openfold3','resident'],['openfold3','positions']]
if phase.startswith('diffcache'):cfg['arms']=[['protenix_v2','baseline'],['protenix_v2','diffcache'],['protenix_constraint','baseline'],['protenix_constraint','diffcache']]
if phase=='esm_offset':cfg['arms']=[['esmfold2_fast','baseline'],['esmfold2_fast','offset'],['esmfold2_full','baseline'],['esmfold2_full','offset']]
if phase=='esm_memory':
 cfg['arms']=[['esmfold2_fast','cache4g'],['esmfold2_full','cache4g']]
 cfg['control_phase']='esm_offset'
 cfg['control_purpose']='Use the immediately preceding native baseline for numerical equivalence only. Cross-session timing differences do not establish a speedup. Measure active/cache/driver memory on all five binders.'
if phase=='boltz_confirm':cfg['arms']=[['boltz','resident'],['boltz','baseline']]
if phase=='templates':cfg['arms']=[['protenix_v2','baseline'],['protenix_v2','templates'],['protenix_v2','templates_diffcache']]
if phase=='compute_cache':cfg['arms']=[['protenix_v2','baseline'],['protenix_v2','diffcache'],['protenix_v2','templates'],['protenix_v2','templates_diffcache'],['protenix_constraint','baseline'],['protenix_constraint','diffcache']]
if phase=='precision_probe':
 cfg['arms']=[['protenix_v2','baseline'],['protenix_v2','trunk_bf16']]
 cfg['selected_rows']=cfg['selected_rows'][:1]
 cfg['probe_policy']='One paired 64aa binder/SUMO96 screen, seed42 plus warmup, no cProfile. Expand to five binders only if faster and within the unchanged numerical gate. No promotion from one pair.'
cfg['numerical_gate']='Paired complete-complex backbone RMSD<=0.1A, binder after target-core alignment<=0.2A; confidence scalar maxdelta<=0.01, mean PAE delta<=0.1A, no extra severe geometry defects. Exactness also reported. Gates selected before running; stronger old monomer gate also reported.'
cfg['timing']='Synchronize all named GPU stages for all benchmark/campaign arms; nested times not additive. Cold load/warmup separately; cProfile diagnostic excluded from normal summaries.'
(frozen/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
from iprotein_mcp.plans import _persist,_script_provenance
python=str(root/'components/control/current/python/bin/python3')
command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','PYTORCH_ENABLE_MPS_FALLBACK=0','OMP_NUM_THREADS=4','VECLIB_MAXIMUM_THREADS=4','MKL_NUM_THREADS=4','KMP_USE_SHM=0','HF_HUB_OFFLINE=1','TRANSFORMERS_OFFLINE=1','TOKENIZERS_PARALLELISM=false','/usr/bin/caffeinate','-dimsu',python,str(frozen/'run.py'),str(frozen/'config.json')]
engines=list(dict.fromkeys(e for e,v in cfg['arms']))
normalized=dict(workflow='runtime_benchmark',engines=engines,runtime_python_paths=[cfg['engines'][e]['python'] for e in engines],output=str(out),msa_policy=cfg['protocol'],scheduler='One resident engine process per arm; serial shared GPU lease; five different binders/same SUMO target; preserved seeds42-46',steps=[dict(stage=phase,command=command,cwd=str(out))])
files=list(frozen.iterdir())+[Path(t['msa']) for t in cfg['targets'].values()]+[Path(cfg['engines'][e]['python']) for e in engines]
plan=_persist('desktop_runtime_benchmark','paper-binder-matrix',normalized,command,'apple_gpu_exclusive',_script_provenance(files));(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(plan['id'],plan['sha256'])
