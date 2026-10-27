"""Freeze the exact Figure2a targets and register a managed benchmark plan."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from common import save,sha
p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,required=True);p.add_argument('--runtime-root',type=Path,default=Path.home()/'.iproteinstudio');p.add_argument('--output',type=Path);a=p.parse_args()
repo=a.repository.resolve();root=a.runtime_root.resolve();source=Path(__file__).resolve().parent
out=(a.output or repo/'Validation/output/esmfold2_600_figure2a_v1').resolve();out.mkdir(parents=True,exist_ok=False)
frozen=out/'frozen';shutil.copytree(source,frozen,ignore=shutil.ignore_patterns('__pycache__'))
target_path=repo/'Validation/output/prediction_scale_v1/targets.json';targets=json.loads(target_path.read_text())
assert list(targets)==['smt3','t4_lysozyme','mbp','citrate_synthase']
assert [v['length'] for v in targets.values()]==[96,164,370,916]
for target in targets.values():assert len(target['sequence'])*target['copies']==target['length']
shutil.copy2(target_path,frozen/'targets.json');protocol=json.loads((source/'protocol.json').read_text())
blocks=[dict(id=target+'_'+arm['name'],target=target,engine='esmfold2-600-mlx',**arm) for target in targets for arm in protocol['arms']]
source_hashes={str(p.relative_to(frozen)):sha(p) for p in frozen.rglob('*') if p.is_file()}
cfg=dict(experiment=protocol['experiment'],output=str(out),protocol=protocol,targets=targets,blocks=blocks,targets_sha256=sha(target_path),source_hashes=source_hashes,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),source_worktree_dirty=True,original_targets_path=str(target_path),runtime_root=str(root))
save(frozen/'config.json',cfg);save(out/'manifest.json',cfg)
os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
from iprotein_mcp.plans import _persist,_script_provenance
command=['/usr/bin/env','PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','PYTORCH_ENABLE_MPS_FALLBACK=0','OMP_NUM_THREADS=4','VECLIB_MAXIMUM_THREADS=4','KMP_USE_SHM=0','TOKENIZERS_PARALLELISM=false','/usr/bin/caffeinate','-dimsu',str(root/'components/control/current/python/bin/python3'),str(frozen/'run.py'),str(frozen/'config.json')]
workloads=[dict(predictors=['esmfold2-600-mlx'],jobs=[dict(name=k,chains=[dict(id=c,kind='protein',sequence=t['sequence'],msa='empty') for c in 'AB'[:t['copies']]])],max_parallel=1,batch_size=1,diffusion_samples=1) for k,t in targets.items()]
normalized=dict(workflow='runtime_benchmark',display_name='Figure 2a: ESMFold2-600, four targets, resident seeds42–46, memory controls',engines=['esmfold2-600-mlx'],runtime_python_paths=[str(root/'venvs/NanoHunter_esmfold2/bin/python')],output=str(out),memory_policy='override',memory_workloads=workloads,scheduler='Exclusive Studio lease; eight serial resident blocks, each warmup then five seeds',msa_policy='Explicit sequence-only; the experimental 600M model has no MSA encoder',steps=[dict(stage='esm600_figure2a',command=command,cwd=str(out))])
files=[p for p in frozen.rglob('*') if p.is_file()]
plan=_persist('desktop_runtime_benchmark','esm600-figure2a',normalized,command,'apple_gpu_exclusive',_script_provenance(files))
save(out/'plan.json',plan);print(json.dumps({k:plan[k] for k in ('id','sha256')}))
