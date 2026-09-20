"""Paired full-setting cached-MSA diagnostic through Studio's shared job broker."""
import argparse,json,os,shutil,sys
from pathlib import Path
from datetime import datetime,timezone
from worker import atomic,sha
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
V2=REPO/'Validation/output/apple_runtime_throughput_v2';OUT=REPO/'Validation/output/apple_runtime_release_v4'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('engine',choices=['protenix','constraint','intellifold-flash','intellifold-full','openfold']);a=ap.parse_args()
 engine='intellifold' if a.engine.startswith('intellifold') else a.engine
 managed=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(managed)
 sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
 from server import MCPServer
 from iprotein_mcp.plans import _persist,_script_provenance
 server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
 out=OUT/(a.engine+'_msa_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir();f=out/'frozen';f.mkdir()
 for p in HERE.iterdir():
  if p.suffix in ('.py','.json'):shutil.copy2(p,f/p.name)
 msa=f/'colabfold_main.a3m';shutil.copy2(managed/'msa_cache/00e99841616c44295043375bc0ba6286.a3m',msa)
 case=json.loads((HERE.parent/'apple_runtime_throughput_v1/manifest.json').read_text())['cases'][1]
 assert msa.read_text().splitlines()[1]==case['sequence']
 case.update(msa=str(msa),msa_sha256=sha(msa),warmup=False)
 seals={}
 for arm in ('baseline','candidate'):
  p=f/(arm+'.seal.json');shutil.copy2(V2/f'{engine}-{arm}.seal.json',p);seals[arm]=str(p)
 shutil.copy2(V2/f'{engine}.source.json',f/'source.seal.json')
 root=V2/'roots'/engine;baseline='2.6.0' if engine in ('intellifold','openfold') else '2.7.1'
 blocks=[dict(id=arm,runtime=arm,torch_version=version,engine=a.engine,seed=42,threads=4,use_msa=True,cases=[case]) for arm,version in [('baseline',baseline),('candidate','2.14.0')]]
 cfg=dict(output=str(out),root=str(root),scripts=str(root/'scripts'),managed_root=str(managed),seals=seals,source_seal=str(f/'source.seal.json'),blocks=blocks,timing_policy='One first prediction per runtime, accuracy diagnostic only; not a steady-state throughput benchmark.')
 atomic(f/'run.json',cfg);atomic(out/'workflow_guide.json',guide)
 modeldir={'constraint':'protenix_constraint','openfold':'openfold3'}.get(engine,engine)
 assets=[p for p in (managed/'models'/modeldir).rglob('*') if p.is_file() and p.suffix in ('.pt','.ckpt','.pkl','.json','.npz','.safetensors')]
 cmd=['/usr/bin/caffeinate','-dimsu',sys.executable,str(f/'coordinator.py'),'--manifest',str(f/'run.json')]
 plan=_persist('desktop_runtime_benchmark','validation-runtime-benchmark',dict(workflow='runtime_benchmark',output=str(out),scheduler='Serial full-setting paired MSA predictions under shared GPU lease',steps=[dict(stage='runtime-benchmark',command=cmd,cwd=str(out))]),cmd,'apple_gpu_exclusive',_script_provenance([p for p in f.iterdir() if p.is_file()]+assets+[Path(sys.executable).resolve()]))
 atomic(out/'plan.json',plan)
 job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});atomic(out/'submitted.json',job);print(json.dumps(dict(output=str(out),job=job)))
if __name__=='__main__':main()
