"""Freeze the experiment and submit through Studio's exclusive GPU broker."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.dont_write_bytecode=True
from common import atomic,sha,verify_inventory
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=ROOT/'Validation/output/esmfold2_fast_v1'
PREVIOUS=ROOT/'Validation/output/esmfold2_mlx_update_v1'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',action='store_true');a=ap.parse_args()
    managed=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio')).resolve();os.environ['NANOHUNTER_ROOT']=str(managed)
    if os.environ.get('IPROTEINSTUDIO_AGENT_ROOT'):raise RuntimeError('Shared broker required')
    sys.path.insert(0,str(managed/'mcp'))
    from server import MCPServer
    from iprotein_mcp.plans import _persist,_script_provenance
    server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
    invpath=PREVIOUS/'runtime_inventory.json';fastinv=OUT/'fast_inventory.json'
    inventory=json.loads(invpath.read_text())+json.loads(fastinv.read_text());verify_inventory(inventory)
    phase=OUT/('paired_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));frozen=phase/'frozen';frozen.mkdir(parents=True)
    for p in HERE.iterdir():
        if p.suffix in ('.py','.json'):shutil.copy2(p,frozen/p.name)
    protocol=json.loads((frozen/'manifest.json').read_text())
    cfg=dict(output=str(phase),protocol=protocol,host_python=str(PREVIOUS/'venv/bin/python'),pythons={'new':str(PREVIOUS/'candidate-venv/bin/python')},sources={'new':str(PREVIOUS/'sources/new')},assets=str(ROOT.parent/'iProteinHunter-beta/output/esmfold2_compute_allocation/assets'),fast_assets=str(OUT/'assets/ESMFold2-Fast'),inventory=inventory,context_configs={})
    cfg['blocks']=[]
    for context in protocol['contexts']:
        for profile in protocol['profiles']:
            for backend in ('pytorch','mlx'):
                bid=context+'_'+profile['id']+'_'+backend
                cfg['blocks'].append(dict(**{k:v for k,v in profile.items() if k!='id'},id=bid,context=context,backend=backend,arm='new',fold_dtype='float32',warmups=0,repeats=2,output=str(phase/'blocks'/bid)))
    for context,chains in protocol['contexts'].items():
        contextout=phase/'contexts'/context;(contextout/'inputs').mkdir(parents=True)
        ref=contextout/'inputs/reference.json';shutil.copy2(PREVIOUS/'inputs/reference.json',ref)
        cfg['inventory'].append(dict(path=str(ref),sha256=sha(ref)))
        contextcfg=dict(cfg,output=str(contextout),context=context,protocol=dict(protocol,chains=chains,sequence=''.join(chains.values())))
        contextpath=frozen/(context+'.json');atomic(contextpath,contextcfg);cfg['context_configs'][context]=str(contextpath)
    atomic(frozen/'run.json',cfg);atomic(phase/'workflow_guide.json',guide)
    atomic(phase/'host.json',{k:subprocess.check_output(c,text=True).strip() for k,c in {'chip':['sysctl','-n','machdep.cpu.brand_string'],'memory':['sysctl','-n','hw.memsize'],'os':['sw_vers'],'commit':['git','-C',str(ROOT),'rev-parse','HEAD']}.items()})
    command=['/usr/bin/caffeinate','-dimsu',sys.executable,str(frozen/'coordinator.py'),'--config',str(frozen/'run.json')]
    provenance=_script_provenance(list(frozen.iterdir())+[invpath,fastinv,Path(sys.executable).resolve()])
    normalized=dict(workflow='runtime_benchmark',output=str(phase),scheduler='serial two-call model blocks under shared exclusive GPU lease',msa_policy=protocol['msa_policy'],steps=[dict(stage='esmfold2-fast',command=command,cwd=str(phase))])
    plan=_persist('desktop_runtime_benchmark','esmfold2-fast',normalized,command,'apple_gpu_exclusive',provenance);atomic(phase/'plan.json',plan)
    print(json.dumps(dict(output=str(phase),plan_id=plan['id'],plan_sha256=plan['sha256'])),flush=True)
    if a.start:
        job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});atomic(phase/'submitted.json',job);print(json.dumps(job),flush=True)

if __name__=='__main__':main()
