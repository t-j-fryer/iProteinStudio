"""Freeze experiment and create a reviewed, broker-managed preflight plan."""
import json,os,sys,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;repo=HERE.parents[2]
out=repo/'Validation/output/sumo_request_overhead_v1_final';out.mkdir(parents=True,exist_ok=False)
frozen=out/'frozen';frozen.mkdir()
for p in HERE.glob('*.py'):shutil.copy2(p,frozen/p.name)
cfg=json.loads((repo/'Validation/output/sumo_model_matrix_exact_v1/frozen/config.json').read_text())
cfg.update(output=str(out),arms=[['openfold3','w0_keep_features_keyed'],['intellifold_full','ccd_interleaved']],
 protocol='SUMO96 monomer,128-row cached alignment,unchanged reduced steps/recycles,seeds42-46 plus warmup42; OpenFold separate diagnostic42; IntelliFold Full alternates uncached/cached same-seed requests in one resident session, order reversed on odd seeds; one load per arm; serialized shared GPU lease; no app defaults changed',
 baseline=str(repo/'Validation/output/sumo_model_matrix_exact_v1'),
 hypotheses=['OpenFold loader spawn overhead','Lightning CPU/MPS lifecycle','IntelliFold chemical dictionary reuse'],
 extensions='Profile then test deterministic preparation reuse and bounded CPU prefetch where material; no stochastic-feature cache without validation',
 equivalence_gate='Prefer identical features/coordinates/scores. Any deviation must be reported and investigated before promotion; core RMSD and CA-lDDT vs3QHT assessed. No geometry degradation. No speed claim from diagnostic replay.')
(frozen/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
root=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
from iprotein_mcp.plans import _persist,_script_provenance
py=str(root/'components/control/current/python/bin/python3')
command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','PYTORCH_ENABLE_MPS_FALLBACK=0','OMP_NUM_THREADS=4','VECLIB_MAXIMUM_THREADS=4','MKL_NUM_THREADS=4','KMP_USE_SHM=0','HF_HUB_OFFLINE=1','TRANSFORMERS_OFFLINE=1','TOKENIZERS_PARALLELISM=false','/usr/bin/caffeinate','-dimsu',py,str(frozen/'run.py'),str(frozen/'config.json')]
engines=list(dict.fromkeys(e for e,v in cfg['arms']))
normalized=dict(workflow='runtime_benchmark',engines=engines,runtime_python_paths=[cfg['engines'][e]['python'] for e in engines],output=str(out),msa_policy=cfg['protocol'],scheduler='Sequential isolated resident processes; OpenFold bounded prefetch comparison uses one warmup then one directory-style request with five seeds; no overlapping GPU models',steps=[dict(stage='overhead-screen',command=command,cwd=str(out))])
files=list(frozen.iterdir())+[Path(cfg['msas']['128'])]+[Path(cfg['engines'][e]['python']) for e in engines]
plan=_persist('desktop_runtime_benchmark','sumo-overhead',normalized,command,'apple_gpu_exclusive',_script_provenance(files));(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(plan['id'],plan['sha256'])
