"""Fixed validation plan factory, no arbitrary-command interface."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from worker import atomic,sha
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/apple_runtime_throughput_v2'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('engine',choices=['intellifold-flash','intellifold-full','protenix','constraint','nesso','openfold','rfd3','antifold']);ap.add_argument('--stage',choices=['smoke','repeat','profile','buckets','esm','threads','cache','rng','ccd','attention','tape','steady','kernel','init','metal','metalround'],default='smoke');ap.add_argument('--reuse-reference',action='store_true');ap.add_argument('--reverse-order',action='store_true');ap.add_argument('--runtime',choices=['baseline','candidate'],default='candidate');ap.add_argument('--start',action='store_true');a=ap.parse_args()
 allowed={'metalround':{'rfd3'},'metal':{'rfd3'},'init':{'openfold'},'kernel':{'rfd3'},'steady':{'antifold'},'buckets':{'intellifold-flash','intellifold-full'},'cache':{'protenix','constraint'},'esm':{'nesso'},'ccd':{'nesso'},'attention':{'rfd3','openfold'},'rng':{'intellifold-flash','intellifold-full','protenix','constraint'},'tape':{'intellifold-flash','intellifold-full','protenix','constraint'}}
 if a.stage in allowed and a.engine not in allowed[a.stage]:raise RuntimeError('Stage is not implemented for this engine')
 if a.stage=='threads' and a.engine=='rfd3':raise RuntimeError('Torch thread experiment does not tune MLX')
 if os.environ.get('IPROTEINSTUDIO_AGENT_ROOT'):raise RuntimeError('Real shared broker root required')
 managed=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio')).resolve();os.environ['NANOHUNTER_ROOT']=str(managed)
 sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
 from server import MCPServer
 from iprotein_mcp.plans import _persist,_script_provenance
 server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
 if a.stage not in ('smoke','profile','rng','tape','kernel'):
  screens=[json.loads(p.read_text()) for p in OUT.glob(a.engine+'_smoke_*/analysis.json')]
  replay_cases=set()
  for p in OUT.glob(a.engine+'_tape_*/analysis.json'):
   replay=json.loads(p.read_text())
   if replay.get('complete') and replay.get('passed'):replay_cases.update(x['name'] for x in replay['pairs'])
  def acceptable(r):
   if not r.get('complete') or r.get('errors'):return False
   if r.get('passed') or (a.runtime=='baseline' and 'baseline' in r.get('blocks_audited',[])):return True
   failed={x['name'] for x in r.get('pairs',[]) if not x['passed']}
   return bool(failed) and failed.issubset(replay_cases)
  if not any(acceptable(r) for r in screens):raise RuntimeError('A complete audited screen is required; candidate requires direct or matched-random-draw equivalence')
 engine=a.engine.split('-')[0] if a.engine.startswith('intellifold') else a.engine
 out=OUT/(a.engine+'_'+a.stage+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir();f=out/'frozen';f.mkdir()
 for p in HERE.iterdir():
  if p.suffix in ('.py','.json'):shutil.copy2(p,f/p.name)
 root=OUT/'roots'/engine
 source=f/'source.seal.json';shutil.copy2(OUT/f'{engine}.source.json',source)
 seals={}
 for arm in ('baseline','candidate'):
  p=f/(arm+'.seal.json');shutil.copy2(OUT/f'{engine}-{arm}.seal.json',p);seals[arm]=str(p)
 baseline={'intellifold':'2.6.0','protenix':'2.7.1','constraint':'2.7.1','nesso':'2.11.0','openfold':'2.6.0','antifold':'2.2.0','rfd3':None}[engine]
 if engine=='rfd3':
  # Torch is preprocessing-only in this MLX comparison; discover exact pinned package metadata without importing it.
  site=OUT/'environments/rfd3-baseline/lib/python3.12/site-packages';baseline=next(site.glob('torch-*.dist-info')).name.removesuffix('.dist-info').split('-')[1]
 fixtures=json.loads((HERE.parent/'apple_runtime_throughput_v1/manifest.json').read_text())['cases'];cases=[dict(**fixtures[0],warmup=True)]+[dict(**x,warmup=False) for x in fixtures]
 seed=43 if a.stage=='repeat' else 42
 configs=[('baseline','baseline',baseline,None),('candidate','candidate',baseline if engine=='rfd3' else '2.14.0',None)]
 if a.stage in ('repeat','steady'):configs=configs[::-1]
 if a.stage=='steady':cases=[dict(**x,warmup=True) for x in fixtures]+[dict(**x,warmup=False) for _ in range(4) for x in fixtures]
 if a.stage=='profile':configs=[('profile','candidate',baseline if engine=='rfd3' else '2.14.0',None)];cases=[dict(**fixtures[0],warmup=True),dict(**fixtures[1],warmup=False,profile=True)]
 if a.stage in ('buckets','esm','cache','ccd','attention','init','metal','metalround'):configs=[('reference','candidate','2.14.0',None),('variant','candidate','2.14.0',{'buckets':'buckets128','esm':'esm_backbone','cache':'diffusion_cache','ccd':'ccd_cache','attention':'sparse_sdpa','init':'checkpoint_init','metal':'sparse_metal','metalround':'sparse_metal_round'}[a.stage])]
 if a.stage=='kernel':configs=[('kernel','candidate',baseline,None)];cases=[]
 if a.reverse_order:
  if a.reuse_reference:raise RuntimeError('Reversed order requires a contemporaneous pair')
  configs=configs[::-1]
 blocks=[dict(diagnostic=a.stage if a.stage in ('rng','kernel') else None,fixtures=str(OUT/'fixtures'),id=i,runtime=r,torch_version=v,variant=variant,engine=a.engine,seed=seed,threads=4,cases=cases) for i,r,v,variant in configs]
 if a.stage=='tape':
  blocks[0]['random_tape']='capture';blocks[1]['random_tape']='replay'
  # Diagnostics have no timing claim: avoid repeated warmups. Full IntelliFold
  # only needs its failed SUMO case; its ubiquitin comparison already passed.
  selected=fixtures[1:] if a.engine=='intellifold-full' else fixtures
  for block in blocks:block['cases']=[dict(**x,warmup=False) for x in selected]
 if a.stage=='threads':
  blocks=[dict(id=f'threads{n}',runtime='candidate',torch_version='2.14.0',variant=None,engine=a.engine,seed=42,threads=n,cases=cases) for n in ((4,1) if a.runtime=='candidate' else (1,4))]
 if engine=='rfd3':
  for block in blocks:block['torch_version']=baseline
 if a.runtime=='baseline' and a.stage not in ('smoke','repeat','rng'):
  for block in blocks:block.update(runtime='baseline',torch_version=baseline)
 cfg=dict(output=str(out),root=str(root),managed_root=str(managed),seals=seals,source_seal=str(source),blocks=blocks)
 if a.reuse_reference:
  if a.stage not in ('buckets','cache','attention','ccd','esm','init','metal','metalround'):raise RuntimeError('Reference reuse is only for exploratory implementation screens')
  wanted=blocks[0]
  choices=[]
  for prior in sorted(OUT.glob(a.engine+'_smoke_*')):
   if not (prior/'completed.json').exists() or not (prior/'analysis.json').exists():continue
   audit=json.loads((prior/'analysis.json').read_text())
   if audit.get('errors'):continue
   progress=json.loads((prior/'progress.json').read_text());key=wanted['runtime']
   if key in progress:choices.append(Path(progress[key]))
  if not choices:raise RuntimeError('No audited completed runtime reference')
  ref=choices[-1];saved=json.loads((ref.parent/(ref.name+'.request.json')).read_text())
  for key in ('engine','torch_version','threads','seed','cases'):
   if saved[key]!=wanted[key]:raise RuntimeError('Reference scientific/workload mismatch: '+key)
  cfg['reused_reference']=dict(id=wanted['id'],output=str(ref),request=str(ref.parent/(ref.name+'.request.json')),completed_sha256=sha(ref/'completed.json'),timing_caveat='Earlier process block, not a contemporaneous timing control; exploratory implementation rejection screen only')
  cfg['blocks']=blocks[1:]
 atomic(f/'run.json',cfg);atomic(out/'workflow_guide.json',guide)
 atomic(out/'host.json',{k:subprocess.check_output(c,text=True).strip() for k,c in {'chip':['sysctl','-n','machdep.cpu.brand_string'],'memory':['sysctl','-n','hw.memsize'],'os':['sw_vers'],'commit':['git','-C',str(REPO),'rev-parse','HEAD']}.items()})
 # Full read-only checkpoint/data inventory needed by these two monomer fixtures.
 assets=[]
 modeldir={'intellifold':'intellifold','protenix':'protenix','constraint':'protenix_constraint','openfold':'openfold3'}.get(engine)
 if modeldir:
  for p in (managed/'models'/modeldir).rglob('*'):
   if p.is_file() and p.suffix in ('.pt','.ckpt','.pkl','.json','.npz','.safetensors'):assets.append(p)
 if engine=='nesso':
  base=managed/'components/nesso/v1.0.0-mps-1';assets=[base/'receipt.json',*[base/p for p in json.loads((base/'receipt.json').read_text())['files'] if not p.startswith('venv/')]]
 if engine=='antifold':assets=[root/'src/AntiFold/models/model.pt',*list((OUT/'fixtures').glob('*.pdb'))]
 if engine=='rfd3':assets=list((managed/'rfd3/weights').glob('*safetensors*'))
 command=['/usr/bin/caffeinate','-dimsu',sys.executable,str(f/'coordinator.py'),'--manifest',str(f/'run.json')]
 provenance=_script_provenance([p for p in f.iterdir() if p.is_file()]+assets+[Path(sys.executable).resolve()])
 normalized=dict(workflow='runtime_benchmark',output=str(out),scheduler='serial model-owned blocks under shared exclusive GPU lease',steps=[dict(stage='runtime-benchmark',command=command,cwd=str(out))])
 plan=_persist('desktop_runtime_benchmark','validation-runtime-benchmark',normalized,command,'apple_gpu_exclusive',provenance);atomic(out/'plan.json',plan)
 print(json.dumps(dict(output=str(out),plan_id=plan['id'],plan_sha256=plan['sha256'])),flush=True)
 if a.start:
  job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});atomic(out/'submitted.json',job);print(json.dumps(job),flush=True)
if __name__=='__main__':main()
