"""Freeze a qualification attempt and submit via the shared MCP broker."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys
from datetime import datetime, timezone
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',action='store_true');ap.add_argument('--mode',choices=['adapter','routes','workflows'],default='adapter');a=ap.parse_args()
    managed=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(managed)
    sys.path.insert(0,str(managed/'mcp'))
    from server import MCPServer
    from iprotein_mcp.plans import _persist,_script_provenance
    server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
    out=ROOT/'Validation/output/esmfold2_app_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    frozen=out/'frozen';shutil.copytree(HERE,frozen,ignore=shutil.ignore_patterns('__pycache__'))
    scripts=out/'root/scripts';shutil.copytree(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts',scripts,ignore=shutil.ignore_patterns('__pycache__'))
    workflows=out/'workflows'
    for name in ('rfd3','rfd3_overlay'):
        shutil.copytree(ROOT/'Sources/iProteinStudio/Resources'/name,workflows/name,ignore=shutil.ignore_patterns('__pycache__'))
    package=ROOT/'build/esmfold2-publisher/runtime-v2'
    assets=out/'root/models/esmfold2';assets.mkdir(parents=True)
    base=ROOT.parent/'iProteinHunter-beta/output/esmfold2_compute_allocation/assets'
    for name in ('ESMC-6B','ESMFold2'):
        subprocess.run(['/bin/cp','-cR',str(base/name),str(assets/name)],check=True)
    subprocess.run(['/bin/cp','-cR',str(ROOT/'Validation/output/esmfold2_fast_v1/assets/ESMFold2-Fast'),str(assets/'ESMFold2-Fast')],check=True)
    engine_python=package/'python/bin/python3'
    venv=out/'root/venvs/NanoHunter_esmfold2';venv.parent.mkdir(parents=True);venv.symlink_to(package/'python')
    protocol=json.loads((ROOT/'Validation/experiments/esmfold2_fast_v1/manifest.json').read_text())
    import yaml
    inputs=out/'inputs';inputs.mkdir()
    for name,chains in protocol['contexts'].items():
        (inputs/(('a_' if name=='monomer' else 'b_')+name+'.yaml')).write_text(yaml.safe_dump({'version':1,'sequences':[{'protein':dict(id=k,sequence=v,msa='empty')} for k,v in chains.items()]}))
    ligand={'version':1,'sequences':[{'protein':{'id':'A','sequence':protocol['contexts']['complex']['A'],'msa':'empty'}},{'ligand':{'id':'B','smiles':'O=C(O)CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@H]12'}}]}
    (inputs/'c_biotin.yaml').write_text(yaml.safe_dump(ligand))
    for n in range(3):shutil.copy2(inputs/'b_complex.yaml',inputs/f'd_repeat_{n:02}.yaml')
    # The route qualification uses installed portable scientific tools through a
    # private view; no application runtime or active campaign files are changed.
    for name in ('components', 'src', 'rfd3'):
        if (managed/name).exists(): (out/'root'/name).symlink_to(managed/name)
    for name in ('NanoHunter_boltz', 'NanoHunter_lasermpnn'):
        (out/'root/venvs'/name).symlink_to((managed/'venvs'/name).resolve())
    for item in (managed/'models').iterdir():
        if item.name != 'esmfold2': (assets.parent/item.name).symlink_to(item.resolve())
    msa=out/'msa';msa.mkdir()
    shutil.copy2(ROOT/'Validation/output/esmfold2_mlx_update_v1/inputs/smt3.a3m',msa/'smt3.a3m')
    cfg=dict(mode=a.mode, output=str(out),root=str(out/'root'),package=str(package),package_sha256=sha(package/'runtime.json'),python=str(engine_python),adapter=str(scripts/'esmfold2_predict.py'),inputs=str(inputs),protocol=json.loads((frozen/'manifest.json').read_text()))
    (frozen/'run.json').write_text(json.dumps(cfg,indent=2)+'\n');(out/'workflow_guide.json').write_text(json.dumps(guide,indent=2)+'\n')
    paths=[p for folder in (frozen,scripts,inputs,msa,workflows) for p in folder.rglob('*') if p.is_file()]+[package/'runtime.json']
    command=[str(engine_python if a.mode=='adapter' else out/'root/venvs/NanoHunter_boltz/bin/python'),str(frozen/('coordinator.py' if a.mode=='adapter' else 'routes.py' if a.mode=='routes' else 'workflows.py')),'--config',str(frozen/'run.json')]
    normalized=dict(workflow='runtime_benchmark',output=str(out),scheduler='serial portable ESMFold2 directory requests under exclusive GPU lease',msa_policy='explicit sequence-only',steps=[dict(stage='esmfold2-portable',command=command,cwd=str(out))])
    plan=_persist('desktop_runtime_benchmark','esmfold2-portable',normalized,command,'apple_gpu_exclusive',_script_provenance(paths))
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),plan_id=plan['id'],plan_sha256=plan['sha256'])),flush=True)
    if a.start:
        job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});(out/'submitted.json').write_text(json.dumps(job,indent=2)+'\n');print(json.dumps(job),flush=True)
if __name__=='__main__':main()
