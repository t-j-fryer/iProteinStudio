"""Freeze the shipping code and prepare a managed release-qualification job."""
import json,os,shutil,sys
from pathlib import Path
from datetime import datetime,timezone

def main():
    repo=Path(__file__).resolve().parents[3];root=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio'))
    output=repo/'Validation/output/product_efficiency_release_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    frozen=output/'frozen';frozen.mkdir(parents=True)
    shutil.copytree(repo/'Sources/iProteinStudio/Resources/pipeline/scripts',frozen/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    check='soak.py' if '--soak-only' in sys.argv else 'qualify.py'
    shutil.copy2(Path(__file__).with_name(check),frozen/check)
    source=json.loads((repo/'Validation/output/biotin_fixed_iterative_v1/run_20261016_repair1/frozen/config.json').read_text())
    selected=[r for g in ('boltz','rfd3') for r in [x for x in source['roots'] if x['generator']==g][:2]]
    inputs=[]
    for i,row in enumerate(selected):
        dest=frozen/f'input_{i}.pdb';shutil.copy2(row['pdb'],dest);inputs.append(str(dest))
    cfg=dict(root=str(root),output=str(output),scripts=str(frozen/'scripts'),inputs=inputs,smiles=source['smiles'],
             geometry=source['geometry'],prediction_settings=json.loads((frozen/'scripts/prediction_profiles.json').read_text()))
    path=frozen/'config.json';path.write_text(json.dumps(cfg,indent=2)+'\n')
    sys.path.insert(0,str(root/'mcp'))
    from iprotein_mcp.plans import _persist,_script_provenance
    from iprotein_mcp.broker import start_job
    py=root/'venvs/NanoHunter_boltz/bin/python'
    command=[str(py),'-B',str(frozen/check),str(path)]
    normalized=dict(workflow='runtime_benchmark',output=str(output),engines=['boltz','lasermpnn'],
        runtime_python_paths=[str(py),str(root/'venvs/NanoHunter_lasermpnn/bin/python')],
        msa_policy='empty; saved designed biotin binders',scheduler='one exclusive Studio lease; one resident Boltz worker; CPU serial versus resident2 bounded prefetch',
        steps=[dict(stage='release-cpu-soak' if check=='soak.py' else 'release-paired-ligand-qualification',command=command,cwd=str(output))])
    plan=_persist('desktop_runtime_benchmark','release-efficiency-024',normalized,command,'apple_gpu_exclusive',
                  _script_provenance([p for p in frozen.rglob('*') if p.is_file()]))
    (output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    result=dict(output=str(output),id=plan['id'],sha256=plan['sha256'])
    if '--start' in sys.argv:result['job']=start_job(plan['id'],plan['sha256'])['id']
    print(json.dumps(result))

if __name__=='__main__':main()
