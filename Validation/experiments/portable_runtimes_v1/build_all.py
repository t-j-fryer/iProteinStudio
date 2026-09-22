"""Local release assembly only; does not activate or modify installed engines."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];managed=Path.home()/'.iproteinstudio'
out=ROOT/'Validation/output/portable_runtimes_v1';out.mkdir(parents=True,exist_ok=True)
profiles={
 'mpnn':('ligandmpnn','torch,numpy',[('LigandMPNN','src/LigandMPNN')]),
 'boltz':('boltz','torch,boltz,rdkit',[]),
 'intellifold':('intellifold','torch,intellifold,gemmi',[('IntelliFold','src/IntelliFold')]),
 'protenix':('protenix','torch,protenix,rdkit',[('Protenix','src/Protenix')]),
 'protenix_constraint':('protenix_constraint','torch,protenix,rdkit',[('ProtenixConstraint','src/ProtenixConstraint')]),
 'openfold3':('openfold3_mlx','mlx.core,openfold3',[('openfold-3-mlx','src/openfold-3-mlx')]),
 'antifold':('antifold','torch,antifold',[('AntiFold','src/AntiFold')]),
 'lasermpnn':('lasermpnn','torch,torch_scatter,torch_cluster',[('LASErMPNN','src/LASErMPNN')]),
 'nesso':('','torch,nesso,transformers',[]),
 'rfd3':('','torch,mlx.core',[('RFD3','rfd3')]),
}
results=[]
profiles['control']=('', 'json,ssl,sqlite3', [])
for engine,(venv,imports,sources) in profiles.items():
 package=out/(engine+'-portable-v4')
 python=managed/'venvs'/('NanoHunter_'+venv)/'bin/python'
 if engine=='control':python=managed/'toolchains/python/cpython-3.11.13-macos-aarch64-none/bin/python3'
 if engine=='nesso':python=managed/'components/nesso/v1.0.0-mps-1/venv/bin/python'
 if engine=='rfd3':python=managed/'rfd3/.venv/bin/python'
 cmd=[sys.executable,str(ROOT/'tools/build_runtime_package.py'),'--python',str(python),'--engine',engine,'--imports',imports,'--output',str(package)]
 for name,source in sources:cmd+=['--source',name+'='+str(managed/source)]
 if engine in ('protenix_constraint','rfd3'):cmd+=['--standalone-python',str(managed/'toolchains/python/cpython-3.12.10-macos-aarch64-none/bin/python3')]
 if engine=='protenix':cmd+=['--binary','kalign='+str(python.parent/'kalign')]
 mounts={'mpnn': [('sources/LigandMPNN/model_params','src/LigandMPNN/model_params')], 'antifold':[('sources/AntiFold/models','src/AntiFold/models')], 'lasermpnn':[('sources/LASErMPNN/model_weights','src/LASErMPNN/model_weights')], 'rfd3':[('sources/RFD3/checkpoints','rfd3/checkpoints'),('sources/RFD3/weights','rfd3/weights')]}
 for name,legacy in mounts.get(engine,[]):cmd+=['--asset-mount',name+'='+legacy]
 if engine=='rfd3':cmd+=['--runtime-link','sources/RFD3/.venv=../../python']
 log=out/(engine+'-build-v4.log');start=time.monotonic()
 with log.open('w') as stream:r=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT)
 results.append(dict(engine=engine,returncode=r.returncode,seconds=time.monotonic()-start,command=cmd,log=str(log)))
 (out/'build-results-v4.json').write_text(json.dumps(results,indent=2)+'\n');print(engine,r.returncode,flush=True)
