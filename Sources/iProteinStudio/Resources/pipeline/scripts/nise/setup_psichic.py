#!/usr/bin/env python3
"""Install experimental PSICHIC from a portable runtime and verified upstream assets."""
import argparse,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from runtime_package import activate,from_catalog,verify
from psichic_contract import installation,asset_root,protocol,sha256,validate_installation

def install(root,package=None,checksum=None,reuse=None):
    base=installation(root)
    if package:
        if not checksum:raise ValueError('Local package requires its expected manifest checksum')
        base=activate(root,'psichic',package,checksum)
    elif not (base/'runtime.json').is_file():base=from_catalog(root,'psichic')
    else:verify(base,engine='psichic')
    for name,item in protocol()['assets'].items():
        dest=asset_root(root)/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.is_file() and sha256(dest)==item['sha256']:continue
        source=Path(reuse)/name if reuse else None
        if source and source.is_file() and sha256(source)==item['sha256']:
            pending=dest.with_suffix(dest.suffix+'.part');shutil.copyfile(source,pending)
            if sha256(pending)!=item['sha256']:raise ValueError('Asset changed during copy')
            pending.replace(dest)
        else:
            subprocess.run([str(base/'python/bin/python3'),str(Path(__file__).resolve().parent.parent/'download_verified.py'),'--url',item['url'],'--sha256',item['sha256'],'--output',str(dest),'--label','PSICHIC '+name,'--progress-key','psichic'],check=True)
    validate_installation(root)
    print('NHSTATE|psichic|ok|PSICHIC-XL (experimental); ESM on Apple GPU, graph scoring on CPU',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--detect',action='store_true');p.add_argument('--package',type=Path);p.add_argument('--manifest-sha256');p.add_argument('--reuse-assets',type=Path);a=p.parse_args()
    if a.detect:
        try:
            validate_installation(a.root,full=False)
            print('NHSTATE|psichic|ok|PSICHIC-XL (experimental; hashes verified at preflight)')
        except (ValueError,OSError,KeyError,TypeError) as e:
            state='incomplete' if installation(a.root).exists() else 'missing'
            print('NHSTATE|psichic|'+state+'|'+str(e))
    else:install(a.root,a.package,a.manifest_sha256,a.reuse_assets)
