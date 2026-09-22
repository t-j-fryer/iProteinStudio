#!/usr/bin/env python3
"""Verify and activate immutable portable runtimes; never build code on clients."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile,platform
from pathlib import Path
from runtime_transaction import prepare,commit,atomic_json,identity,recover

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()

def relative(name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe runtime package path: '+name)
    return p

def verify(base,expected=None,engine=None,full=True):
    base=Path(base).resolve();manifest=base/'runtime.json'
    if expected and digest(manifest)!=expected:raise ValueError('Runtime manifest checksum mismatch')
    record=json.loads(manifest.read_text())
    if record.get('schema_version')!=1 or (engine and record.get('engine')!=engine):raise ValueError('Unsupported runtime package identity')
    if record.get('contains_weights') is not False:raise ValueError('Runtime packages must exclude model weights')
    for name,entry in record['files'].items():
        p=base/relative(name)
        if base not in p.resolve().parents:raise ValueError('Runtime file escapes package: '+name)
        if 'symlink' in entry:
            if not p.is_symlink() or os.readlink(p)!=entry['symlink'] or not p.exists():raise ValueError('Runtime symlink changed: '+name)
        elif p.is_symlink() or not p.is_file() or p.stat().st_size!=entry['size'] or (full and digest(p)!=entry['sha256']):raise ValueError('Runtime file changed: '+name)
    mounts=record.get('asset_mounts',{})
    for name,legacy in mounts.items():
        p=base/relative(name);relative(legacy)
        if p.exists() or p.is_symlink():
            # Only the installer may add these declared data-only links. They
            # never authorize extra executable files elsewhere in the package.
            if not p.is_symlink():raise ValueError('Asset mount must be a link: '+name)
            managed=base.parents[3] if base.parent.name=='versions' else None
            allowed=managed/'model_assets'/record['engine'] if managed else None
            if allowed is None or allowed not in p.resolve().parents:raise ValueError('Asset mount escapes owned model storage: '+name)
    expected_files=set(record['files'])|{'runtime.json','transaction.json'}|set(mounts)
    extras={str(p.relative_to(base)) for p in base.rglob('*') if (p.is_file() or p.is_symlink()) and '__pycache__' not in p.parts}-expected_files
    if extras:raise ValueError('Uninventoried runtime files: '+str(sorted(extras)[:5]))
    return record

def extract(archive,destination):
    """No absolute names, links outside the archive, devices, hardlinks or duplicates."""
    with tarfile.open(archive,'r:*') as tar:
        seen=set()
        for item in tar.getmembers():
            p=relative(item.name)
            if str(p) in seen:raise ValueError('Duplicate archive member')
            seen.add(str(p))
            if not (item.isfile() or item.isdir() or item.issym()):raise ValueError('Unsafe archive member type')
            if item.issym():
                target=Path(item.linkname)
                if target.is_absolute() or Path(os.path.normpath(str(p.parent/target))).parts[0]=='..':raise ValueError('Archive link escapes root')
        # Python 3.10 has no data filter: perform links last to prevent traversal.
        members=tar.getmembers()
        for item in members:
            if item.issym():continue
            p=destination/relative(item.name)
            if item.isdir():p.mkdir(parents=True,exist_ok=True)
            else:
                p.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(item) as source,p.open('wb') as target:shutil.copyfileobj(source,target)
                p.chmod(item.mode & 0o777)
        for item in members:
            if item.issym():(destination/relative(item.name)).symlink_to(item.linkname)

def activate(root,engine,package,expected,mappings=()):
    identity(engine);root=Path(root).resolve();package=Path(package).resolve()
    recover(root,engine)
    record=verify(package,expected,engine)
    if record.get('architecture') and platform.machine()!=record['architecture']:raise ValueError('Runtime architecture is incompatible with this Mac')
    if record.get('minimum_macos'):
        def version_tuple(v):return tuple(int(x) for x in v.split('.'))+(0,)*(3-len(v.split('.')))
        if platform.system()!='Darwin' or version_tuple(platform.mac_ver()[0])<version_tuple(record['minimum_macos']):raise ValueError('Runtime requires macOS '+record['minimum_macos']+' or newer')
    version=expected[:20]
    current=root/'components'/engine/'current'
    if current.exists() and (current/'runtime.json').is_file() and digest(current/'runtime.json')==expected:
        verify(current,expected,engine);return current.resolve()
    stage=prepare(root,engine,version)
    from runtime_view import clone_file
    shutil.copytree(package,stage,dirs_exist_ok=True,symlinks=True,copy_function=clone_file)
    # prepare's private marker is retained, not part of the shipped inventory.
    verify(stage,expected,engine)
    executable=stage/'python/bin/python3'
    record=json.loads((stage/'runtime.json').read_text())
    code='import importlib; '+ '; '.join('importlib.import_module('+repr(n)+')' for n in record['relocation_imports'])
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([str(executable),'-I','-B','-c',code],check=True,env=env)
    for name,legacy in record.get('asset_mounts',{}).items():
        from runtime_view import clone_file
        # Multiple code locations can refer to the same upstream model folder
        # (AntiFold's CLI source and imported package). They must share one
        # download on a fresh installation, as well as during migration.
        data=root/'model_assets'/engine/expected[:20]/relative(legacy)
        if not data.exists():
            old=root/relative(legacy);data.parent.mkdir(parents=True,exist_ok=True)
            pending=data.with_name(data.name+'.pending')
            if pending.exists():shutil.rmtree(pending)
            if old.is_dir():shutil.copytree(old,pending,symlinks=False,copy_function=clone_file)
            else:pending.mkdir()
            pending.rename(data)
        link=stage/relative(name);link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to(data)
    verify(stage,expected,engine)
    final=commit(root,engine,version,stage,list(mappings))
    atomic_json(root/'receipts'/(engine+'-runtime.json'),dict(schema_version=1,engine=engine,path=str(final),manifest_sha256=expected))
    return final

def from_catalog(root,engine):
    """Catalog is shipped with app, never fetched as executable trust-on-first-use."""
    catalog=Path(__file__).with_name('runtime_releases.json')
    records=json.loads(catalog.read_text())['packages']
    if engine not in records:raise ValueError('No qualified downloadable runtime has been published for '+engine+'. Existing installations remain usable.')
    item=records[engine]
    minimum=tuple(map(int,item.get('minimum_macos','14.0').split('.')))
    actual=tuple(map(int,(platform.mac_ver()[0] or '0.0').split('.')))
    if platform.machine()!='arm64' or (actual+(0,)*3)[:3] < (minimum+(0,)*3)[:3]:
        raise ValueError(engine+' requires Apple silicon and macOS '+item.get('minimum_macos','14.0')+' or newer. Update macOS before installing this profile.')
    if not item['url'].startswith('https://github.com/'):raise ValueError('Runtime release must use approved HTTPS hosting')
    cached=Path(root)/'cache/runtime-packages'/item['archive_sha256'];cached.mkdir(parents=True,exist_ok=True)
    archive=cached/'runtime.tar.gz'
    subprocess.run([sys.executable,str(Path(__file__).with_name('download_verified.py')),'--url',item['url'],'--sha256',item['archive_sha256'],'--output',str(archive),'--label',engine+' runtime'],check=True)
    with tempfile.TemporaryDirectory(dir=cached) as tmp:
        extract(archive,Path(tmp))
        return activate(root,engine,Path(tmp),item['manifest_sha256'],[str(Path(root)/k)+'='+v for k,v in item.get('mappings',{}).items()])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--engine',required=True);p.add_argument('--package',type=Path);p.add_argument('--manifest-sha256');p.add_argument('--mapping',action='append',default=[]);a=p.parse_args()
    if a.package:
        if not a.manifest_sha256:p.error('Local package activation requires explicit --manifest-sha256')
        print(activate(a.root,a.engine,a.package,a.manifest_sha256,a.mapping))
    else:print(from_catalog(a.root,a.engine))
