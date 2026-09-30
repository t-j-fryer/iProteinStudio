"""Broker-owned native CLI acceptance: exact SUMO, odd length and two chains."""
import json,os,sys,shutil,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
if sys.argv[1]=='prepare':
 repo=HERE.parents[2];out=repo/'Validation/output/intellifold_exact_cli_v1';out.mkdir(exist_ok=False)
 root=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
 from iprotein_mcp.plans import _persist,_script_provenance
 shutil.copytree(repo/'Sources/iProteinStudio/Resources/pipeline/scripts',out/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copy2(__file__,out/'qualify_cli.py');(out/'inputs').mkdir()
 cfg=json.loads((repo/'Validation/output/sumo_model_matrix_v1/frozen/config.json').read_text());seq=cfg['sequence']
 for name,chains in [('sumo96',[seq]),('sumo97',[seq+'G']),('two_chains',[seq,'GSGSGSG'])]:
  data='version: 1\nsequences:\n'
  for i,s in enumerate(chains):data+='  - protein:\n      id: '+chr(65+i)+'\n      sequence: '+s+'\n      msa: empty\n'
  (out/'inputs'/f'{name}.yaml').write_text(data)
 py=cfg['engines']['intellifold_full']['python'];(out/'config.json').write_text(json.dumps(dict(python=py,output=str(out)),indent=2))
 control=str((root/'components/control/current/python/bin/python3').resolve());command=['/usr/bin/caffeinate','-dimsu',control,str(out/'qualify_cli.py'),'run']
 normalized=dict(workflow='runtime_benchmark',engines=['intellifold'],runtime_python_paths=[py],output=str(out),msa_policy='Explicit query only; no templates. Three inputs:96,97,103 total protein tokens.',scheduler='Serial native CLI requests, shared GPU lease.',steps=[dict(stage='exact-token-cli',command=command,cwd=str(out))])
 files=[p for p in out.rglob('*') if p.is_file()]+[Path(py)]
 plan=_persist('desktop_runtime_benchmark','exact-token-cli',normalized,command,'apple_gpu_exclusive',_script_provenance(files));(out/'plan.json').write_text(json.dumps(plan,indent=2));print(plan['id'],plan['sha256'])
else:
 out=HERE;cfg=json.loads((out/'config.json').read_text());env=os.environ.copy();env.update(PYTORCH_ENABLE_MPS_FALLBACK='0',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 for name,model in [('full','v2'),('flash','v2-flash')]:
  cmd=[cfg['python'],str(out/'scripts/intellifold_predict.py'),str(out/'inputs'),'--out_dir',str(out/name),'--model',model,'--seed','42','--num_workers','0','--recycling_iters','10','--sampling_steps','200','--num_diffusion_samples','1','--precision','no']
  t=time.perf_counter()
  with (out/(name+'.log')).open('w') as f:r=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
  (out/(name+'_receipt.json')).write_text(json.dumps(dict(returncode=r.returncode,wall_seconds=time.perf_counter()-t,command=cmd),indent=2))
  if r.returncode:raise RuntimeError(name+' CLI failed; inspect its log')
 (out/'completed.json').write_text(json.dumps(dict(models=['full','flash'],inputs=['sumo96','sumo97','two_chains'])))
