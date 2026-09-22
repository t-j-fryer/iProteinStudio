import json,os,subprocess,sys
from pathlib import Path
f=Path(__file__).resolve().parent;sys.path.insert(0,str(f/'scripts'))
from runtime_package import activate,digest
cfg=json.loads(Path(sys.argv[1]).read_text());out=Path(cfg['output']);candidate=Path(cfg['candidate']);package=Path(cfg['package'])
activate(candidate,'lasermpnn',package,digest(package/'runtime.json'),[str(candidate/'src/LASErMPNN')+'=sources/LASErMPNN',str(candidate/'venvs/NanoHunter_lasermpnn')+'=python'])
for arm,root in [('baseline',Path(cfg['root'])),('portable',candidate)]:
 req=dict(root=str(root),output=str(out/arm),engine='lasermpnn',model='lasermpnn',fixture=str(f/'fixture.pdb'));p=out/(arm+'.json');p.write_text(json.dumps(req))
 env={**os.environ,'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4','KMP_USE_SHM':'0','PYTHONPYCACHEPREFIX':'/dev/null'};env.pop('IPROTEINSTUDIO_RUNTIME_BINDINGS',None)
 with (out/(arm+'.log')).open('w') as log:subprocess.run([str(root/'venvs/NanoHunter_lasermpnn/bin/python'),str(f/'sequence_smoke.py'),str(p)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
a=json.loads((out/'baseline/audit.json').read_text());b=json.loads((out/'portable/audit.json').read_text());assert a==b,(a,b)
(out/'audit.json').write_text(json.dumps(dict(passed=True,exact=True,baseline=a,portable=b),indent=2));print('LASErMPNN exact sampled output PASS',flush=True)
