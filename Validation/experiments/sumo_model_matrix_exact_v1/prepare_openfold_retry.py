"""Freeze a corrected OpenFold-only retry without touching original raw outputs."""
import json,os,sys,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;repo=HERE.parents[2];out=repo/'Validation/output/sumo_model_matrix_exact_v1';frozen=out/'retries/openfold3_03';frozen.mkdir(parents=True,exist_ok=False)
root=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
from iprotein_mcp.plans import _persist,_script_provenance
for name in ('worker.py','common.py','intellifold_padding.py','test_worker_spawn.py'):shutil.copy2(HERE/name,frozen/name)
shutil.copy2(repo/'Sources/iProteinStudio/Resources/pipeline/scripts/openfold_query_json.py',frozen/'openfold_query_json.py')
shutil.copy2(out/'frozen/config.json',frozen/'config.json');cfg=json.loads((frozen/'config.json').read_text());py=cfg['engines']['openfold3']['python']
command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','PYTORCH_ENABLE_MPS_FALLBACK=0','OMP_NUM_THREADS=4','VECLIB_MAXIMUM_THREADS=4','MKL_NUM_THREADS=4','KMP_USE_SHM=0','HF_HUB_OFFLINE=1','TRANSFORMERS_OFFLINE=1','TOKENIZERS_PARALLELISM=false','/usr/bin/caffeinate','-dimsu',py,str(frozen/'worker.py'),str(frozen/'config.json'),'openfold3',str(out/'openfold3_retry03')]
normalized=dict(workflow='runtime_benchmark',engines=['openfold3'],runtime_python_paths=[py],output=str(out),msa_policy='Same immutable SUMO query-only/128/full input MSAs and seeds42-46.',scheduler='One resident OpenFold model, sequential submissions; shared GPU lease; spawn-safe benchmark main guard.',steps=[dict(stage='openfold-exact-retry',command=command,cwd=str(out))])
files=list(frozen.iterdir())+[Path(py)]+[Path(p) for p in cfg['msas'].values()]
plan=_persist('desktop_runtime_benchmark','sumo-openfold-retry',normalized,command,'apple_gpu_exclusive',_script_provenance(files));(frozen/'plan.json').write_text(json.dumps(plan,indent=2));print(plan['id'],plan['sha256'])
