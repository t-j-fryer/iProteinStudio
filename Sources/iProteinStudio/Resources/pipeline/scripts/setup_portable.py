#!/usr/bin/env python3
"""Install shipped runtime profiles and separately verified upstream model assets.

Called under setup_pipeline.sh's installer/shared execution lock. No compiler,
Git checkout, pip install, or source patch is executed on the user's machine.
"""
import argparse,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from runtime_package import from_catalog,activate,digest,extract,relative,verify
from runtime_transaction import atomic_json
from engine_registry import engines
HERE=Path(__file__).resolve().parent
ASSETS=json.loads((HERE/'runtime_assets.json').read_text())['assets']
DEPENDENCIES={'abmpnn':['mpnn'],'boltz_affinity':['boltz'],'intellifold_full':['intellifold'],'protenix_v2':['protenix'],'protenix_mini':['protenix']}

def run(command,**kw):subprocess.run([str(v) for v in command],check=True,**kw)
def download(root,item,key):
    path=root/relative(item['path'])
    run([sys.executable,HERE/'download_verified.py','--url',item['url'],'--sha256',item['sha256'],'--output',path,'--label',item['label'],'--progress-key',key])

def install_nesso_assets(root,python):
    sys.path.insert(0,str(HERE/'nise'))
    from nesso_contract import installation,protocol,expected_assets,ASSETS as source,VERSION,sha256,validate_installation
    from setup_nesso import reuse_esm_asset
    base=installation(root);base.mkdir(parents=True,exist_ok=True);p=protocol()
    for name,checksum in expected_assets().items():
        if name.startswith('esm/'):
            repo,revision,remote=p['assets']['esm_repository'],p['assets']['esm_commit'],name[4:]
            if reuse_esm_asset(root,remote,checksum,base/name):continue
        else:
            repo,revision='recursionpharma/nesso',p['assets']['nesso_hf_commit']
            remote='v1.0.0/'+name[6:] if name.startswith('model/') else name
        download(root,dict(path=str((base/name).relative_to(root)),url=f'https://huggingface.co/{repo}/resolve/{revision}/{remote}',sha256=checksum,label='NESSO '+name),'nesso')
    files=[base/name for name in expected_assets()]
    for module in ('nesso','transformers'):files+=sorted((base/'venv/lib').glob('python*/site-packages/'+module+'/**/*.py'))
    atomic_json(base/'receipt.json',dict(version=VERSION,protocol_sha256=sha256(source/'protocol.json'),lock_sha256=sha256(source/'requirements.lock'),patch_sha256=sha256(source/'nesso_mps.patch'),files={str(f.relative_to(base)):dict(sha256=sha256(f),size=f.stat().st_size) for f in files}))
    validate_installation(root)

def install(root,key,local=None):
    descriptors=[d for d in engines().values() if d['component']==key]
    if descriptors:
        print('NHSTEP|'+key+'|5|Installing verified portable '+descriptors[0]['label'],flush=True)
        if local:
            package=local/(key+'-release-final3')
            if not package.exists():package=local/(key+'-release-final2')
            manifest=digest(package/'runtime.json')
            mappings={k:v for d in descriptors for k,v in d['mappings'].items()}
            base=activate(root,key,package,manifest,[str(root/k)+'='+v for k,v in mappings.items()])
        else:base=from_catalog(root,key)
        python=base/'python/bin/python3'
    else:
        base=root/'components'/DEPENDENCIES[key][0]/'current';python=base/'python/bin/python3'
        if not python.is_file():raise ValueError('Install required runtime first: '+str(base))
    for item in ASSETS.get(key,[]):
        if key=='boltz' and item['path'].endswith('mols.tar') and (root/'models/boltz2/mols').is_dir():continue
        download(root,item,key)
    if key=='boltz' and not (root/'models/boltz2/mols').is_dir():
        archive=root/'models/boltz2/mols.tar'
        with tempfile.TemporaryDirectory(dir=archive.parent) as temp:
            extract(archive,Path(temp));os.replace(Path(temp)/'mols',archive.parent/'mols')
        archive.unlink()
    if key=='abmpnn':
        dest=root/'src/LigandMPNN/model_params/abmpnn.pt'
        run([python,HERE/'download_verified.py','--sources',HERE/'abmpnn_sources.json','--output',dest,'--provenance',dest.with_name('abmpnn.source.json'),'--label','AbMPNN checkpoint','--progress-key',key])
    if key=='nesso':install_nesso_assets(root,python)
    if key=='psichic':run([python,HERE/'nise/setup_psichic.py','--root',root])
    if key=='protenix_constraint':
        source=root/'src/ProtenixConstraint'
        atomic_json(root/'models/protenix_constraint/install_receipt.json',dict(product='Protenix Constraint v0.5 — Experimental',model='protenix_base_constraint_v0.5.0',source_commit='4c355be4553512f72453ecbfb65e69f4c35d1413',patch_sha256=digest(root/'patches/protenix_constraint_mps.patch'),zero_substructure_patch_sha256=digest(root/'patches/protenix_constraint_zero_substructure.patch'),substructure_source_sha256=digest(source/'protenix/model/modules/embedders.py'),checkpoint_sha256=ASSETS[key][0]['sha256'],device_policy='native-mps-fp32-no-cpu-fallback',esm='disabled-and-not-installed'))
    if key=='rfd3':
        source=root/'rfd3';weights=source/'weights/rfd3_core.safetensors';expected='736e6f5e11ec70dea58903deb2290031e366d2b0b2478e63208a2541650a04d6'
        if not weights.is_file() or digest(weights)!=expected:
            run([python,source/'export_weights.py'],env={**os.environ,'DEBUG':'false','TOKENIZERS_PARALLELISM':'false'})
        if digest(weights)!=expected:raise ValueError('RFdiffusion3 weight conversion checksum mismatch')
        run([python,source/'rfd3_weight_set.py','--check-artifact',weights])
    # Asset receipts deliberately avoid Git/pip on the client. Runtime identity
    # separately records every executable byte and exact installed dependency.
    assets={i['path']:i['sha256'] for i in ASSETS.get(key,[]) if not i['path'].endswith('/mols.tar')}
    if key=='rfd3':assets['rfd3/weights/rfd3_core.safetensors']=expected
    if key=='abmpnn':assets['src/LigandMPNN/model_params/abmpnn.pt']=json.loads((dest.with_name('abmpnn.source.json')).read_text())['sha256']
    if key=='nesso':
        from nesso_contract import expected_assets,installation
        assets.update({str((installation(root)/name).relative_to(root)):sha for name,sha in expected_assets().items()})
    if key=='psichic':
        from nise.psichic_contract import asset_root,protocol
        assets.update({str((asset_root(root)/name).relative_to(root)):item['sha256'] for name,item in protocol()['assets'].items()})
    atomic_json(root/'receipts'/(key+'.json'),dict(schema_version=2,component=key,portable=True,runtime_component=json.loads((base/'runtime.json').read_text())['engine'],runtime_path=str(base.resolve().relative_to(root)),runtime_manifest_sha256=digest(base/'runtime.json'),assets=assets,complete=True))
    print('NHSTATE|'+key+'|ok|Verified portable runtime and model assets',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--components',required=True);p.add_argument('--local-packages',type=Path);a=p.parse_args()
    root=a.root.resolve();requested=a.components.split(',');ordered=[]
    def add(key):
        for dep in DEPENDENCIES.get(key,[]):add(dep)
        if key not in ordered:ordered.append(key)
    for key in requested:add(key)
    failures=[]
    for key in ordered:
        try:
            if any(d in failures for d in DEPENDENCIES.get(key,[])):raise ValueError('Required component installation failed')
            install(root,key,a.local_packages)
        except Exception as error:
            failures.append(key);print('NHCOMPONENTFAIL|'+key+'|'+str(error),flush=True)
    print('NHDONE|'+('partial|'+' '.join(failures) if failures else 'ok'),flush=True)
    return 2 if failures else 0
if __name__=='__main__':raise SystemExit(main())
