"""Paired scientific relocation checks through Studio's shared execution broker."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/portable_runtimes_v1';managed=Path.home()/'.iproteinstudio';candidate=OUT/'qualification_root'
os.environ['NANOHUNTER_ROOT']=str(managed);sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
out=OUT/('relocation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));f=out/'frozen';f.mkdir(parents=True)
for name in ('worker.py','extra_engines.py','analyse.py','analysis_policy.json','coordinator.py'):
 source=HERE.parent/('apple_runtime_release_v4' if name=='worker.py' else 'apple_runtime_throughput_v2')/name
 shutil.copy2(source,f/name)
shutil.copy2(HERE.parent/'apple_runtime_kernels_v3/boltz_worker.py',f/'boltz_worker.py')
for name in ('relocation_coordinator.py','relocation_worker.py','sequence_smoke.py'):shutil.copy2(HERE/name,f/name)
fixture=REPO/'Validation/output/apple_runtime_throughput_v2/fixtures';shutil.copytree(fixture,f/'fixtures')
shutil.copy2(Path.home()/'NanoHunter/output/nise_fluorescein/phase0/cycle00/L024_ref.pdb',f/'fixtures/fluorescein.pdb')
case=json.loads((HERE.parent/'apple_runtime_throughput_v1/manifest.json').read_text())['cases'][0];case=dict(name='ubiquitin',sequence=case['sequence'],warmup=False,profile=False)
profiles={'boltz':('boltz','venvs/NanoHunter_boltz/bin/python'),'intellifold-flash':('intellifold','venvs/NanoHunter_intellifold/bin/python'),'intellifold-full':('intellifold','venvs/NanoHunter_intellifold/bin/python'),'protenix':('protenix','venvs/NanoHunter_protenix/bin/python'),'constraint':('protenix_constraint','venvs/NanoHunter_protenix_constraint/bin/python'),'openfold':('openfold3','venvs/NanoHunter_openfold3_mlx/bin/python'),'rfd3':('rfd3','rfd3/.venv/bin/python'),'antifold':('antifold','venvs/NanoHunter_antifold/bin/python'),'nesso':('nesso','components/nesso/v1.0.0-mps-1/venv/bin/python')}
blocks=[];files=[p for p in f.rglob('*') if p.is_file()]
for engine,(component,relative) in profiles.items():
 for arm,root in [('baseline',managed),('portable',candidate)]:
  py=root/relative
  version=subprocess.check_output([str(py),'-I','-c','import importlib.metadata; print(importlib.metadata.version("torch"))'],text=True).strip()
  req=dict(engine=engine,component=component,arm=arm,root=str(root),managed_root=str(root),output=str(out/(engine+'-'+arm)),python=str(py.parent.parent.resolve()/'bin'/py.name),torch_version=version,threads=4,seed=42,cases=[case],fixtures=str(f/'fixtures'),runtime='baseline')
  if arm=='portable':
   manifest=(root/'components'/component/'current/runtime.json').resolve();files.append(manifest);req['manifest']=str(manifest)
  blocks.append(req);files.append(py.resolve())
for component,relative,models in [('mpnn','venvs/NanoHunter_ligandmpnn/bin/python',['protein_mpnn','soluble_mpnn','ligand_mpnn','abmpnn']),('lasermpnn','venvs/NanoHunter_lasermpnn/bin/python',['lasermpnn'])]:
 for model in models:
  for arm,root in [('baseline',managed),('portable',candidate)]:
   py=root/relative;blocks.append(dict(engine=component,model=model,component=component,arm=arm,root=str(root),output=str(out/(model+'-'+arm)),python=str(py.parent.parent.resolve()/'bin'/py.name),fixture=str(f/'fixtures'/('fluorescein.pdb' if model in ('ligand_mpnn','lasermpnn') else 'ubiquitin.pdb')),sequence_test=True));files.append(py.resolve())
parser=argparse.ArgumentParser();parser.add_argument('--engines');args=parser.parse_args()
if args.engines:blocks=[r for r in blocks if r['engine'] in args.engines.split(',')]
limits=json.loads((HERE.parent/'apple_runtime_throughput_v2/manifest.json').read_text())['acceptance'];limits['nesso_scalar_absolute_max']=0.001
cfg=dict(output=str(out),blocks=blocks,limits=limits,skip_audit=True);(f/'run.json').write_text(json.dumps(cfg,indent=2));files.append(f/'run.json')
(out/'workflow_guide.json').write_text(json.dumps(guide,indent=2))
command=['/usr/bin/caffeinate','-dimsu',str(managed/'toolchains/python/cpython-3.11.13-macos-aarch64-none/bin/python3'),str(f/'relocation_coordinator.py'),str(f/'run.json')]
plan=_persist('desktop_portable_relocation','portable-runtime-qualification',dict(workflow='portable-relocation',output=str(out),steps=[dict(stage='paired-relocation',command=command,cwd=str(out))]),command,'apple_gpu_exclusive',_script_provenance(list(dict.fromkeys(files))))
(out/'plan.json').write_text(json.dumps(plan,indent=2));job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});(out/'submitted.json').write_text(json.dumps(job,indent=2));print(json.dumps(dict(output=str(out),job=job)),flush=True)
