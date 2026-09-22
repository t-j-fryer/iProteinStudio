"""Expose retained portable components at the legacy paths used by upstream tools.

Views contain immutable code links and private copies of source-local model data.
They do not edit engine code or translate scientific settings.
"""
import json,os,shutil,subprocess,uuid,ctypes
from runtime_package import digest
from pathlib import Path
from engine_registry import engines

def clone_file(source,target):
    source,target=Path(source),Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    # APFS clone is independent copy-on-write, unlike a hardlink.
    if os.uname().sysname=='Darwin':
        clone=ctypes.CDLL(None,use_errno=True).clonefile
        if clone(os.fsencode(source),os.fsencode(target),0)==0:return
    shutil.copy2(source,target)

def overlay(package,legacy,target):
    target.mkdir(parents=True,exist_ok=True)
    names={p.name for p in package.iterdir()} if package.is_dir() else set()
    if legacy.is_dir():names|={p.name for p in legacy.iterdir() if p.name not in ('.git','__pycache__','.venv')}
    for name in sorted(names):
        p=package/name;old=legacy/name;dest=target/name
        if p.is_symlink():dest.symlink_to(p.resolve())
        elif p.is_dir():overlay(p,old,dest)
        elif p.exists():dest.symlink_to(p.resolve())
        elif old.is_dir():shutil.copytree(old,dest,symlinks=False,copy_function=clone_file,ignore=shutil.ignore_patterns('.git','__pycache__','.venv'))
        elif old.is_file():clone_file(old,dest)

def build(root,destination,bindings,code_snapshot=None):
    root=Path(root).resolve();destination=Path(destination)
    spec=dict(root=str(root),bindings=bindings)
    if code_snapshot: spec["code_snapshot"] = code_snapshot
    if destination.exists():
        if json.loads((destination/'view.json').read_text())!=spec:raise ValueError('Runtime view does not match saved bindings')
        for name,expected in json.loads((destination/'assets.json').read_text()).items():
            if digest(destination/name)!=expected:raise ValueError('Retained model data changed: '+name)
        return destination
    stage=destination.with_name(destination.name+'.stage-'+uuid.uuid4().hex);stage.mkdir(parents=True)
    maps={};assets=set()
    if code_snapshot:
        maps.update({name:Path(code_snapshot["path"])/name for name in code_snapshot["entries"]})
    for component,binding in bindings.items():
        maps['components/'+component+'/current']=Path(binding['path'])
    for d in engines().values():
        component=d['component']
        if component in bindings:
            base=Path(bindings[component]['path']);assets.update(d.get('model_paths',[]))
            maps.update({name:base/rel for name,rel in d.get('mappings',{}).items()})
    # Split only ancestors that contain overrides; leave caches/output roots shared.
    def tree(original,target,prefix=''):
        target.mkdir(parents=True,exist_ok=True)
        names={p.name for p in original.iterdir()} if original.is_dir() else set()
        names|={p[len(prefix):].split('/')[0] for p in set(maps)|assets if p.startswith(prefix)}
        for name in sorted(names):
            rel=prefix+name;src=original/name;dst=target/name
            if rel in assets and src.exists():
                if src.is_dir():shutil.copytree(src,dst,symlinks=False,copy_function=clone_file,ignore=shutil.ignore_patterns('__pycache__'))
                else:clone_file(src,dst)
            elif rel in maps:
                if rel.startswith('src/') or rel=='rfd3':
                    overlay(maps[rel],src,dst)
                    for nested,value in maps.items():
                        if nested.startswith(rel+'/'):
                            child=dst/nested[len(rel)+1:];child.parent.mkdir(parents=True,exist_ok=True)
                            if child.exists() or child.is_symlink():raise ValueError('Nested runtime mapping collision')
                            child.symlink_to(value)
                    # Source-local weights are private job data, never links to
                    # a mutable installation. Source code remains package-pinned.
                    for nested in assets:
                        if nested.startswith(rel+'/'):
                            child=dst/nested[len(rel)+1:];original_asset=root/nested
                            if child.is_symlink():child.unlink()
                            elif child.is_dir():shutil.rmtree(child)
                            elif child.exists():child.unlink()
                            if original_asset.is_dir():shutil.copytree(original_asset,child,symlinks=False,copy_function=clone_file)
                            elif original_asset.is_file():clone_file(original_asset,child)
                else:dst.symlink_to(maps[rel])
            elif any(p.startswith(rel+'/') for p in set(maps)|assets):tree(src,dst,rel+'/')
            elif src.exists():dst.symlink_to(src.resolve())
    tree(root,stage)
    inventory={}
    for rel in assets:
        p=stage/rel
        for f in ([p] if p.is_file() else p.rglob('*')):
            if f.is_file():inventory[str(f.relative_to(stage))]=digest(f)
    (stage/'assets.json').write_text(json.dumps(inventory,sort_keys=True)+'\n')
    (stage/'view.json').write_text(json.dumps(spec,indent=2,sort_keys=True)+'\n')
    stage.rename(destination);return destination

def rewrite(command,root,view):
    root=str(Path(root).resolve());view=str(view)
    names=('venvs','src','scripts','rfd3','rfd3_scripts','rfd3_overlay','components','nanohunter_run.sh')
    def one(a):
        if a==root:return view
        if any(a==root+'/'+name or a.startswith(root+'/'+name+'/') for name in names):return view+a[len(root):]
        return a
    return [one(a) for a in command]

def bind_configs(command,root,view,destination):
    """Derive runtime-bound configurations without changing saved requests."""
    def walk(value):
        if isinstance(value,str):return rewrite([value],root,view)[0]
        if isinstance(value,list):return [walk(v) for v in value]
        if isinstance(value,dict):return {k:walk(v) for k,v in value.items()}
        return value
    result=[];destination=Path(destination)
    for arg in command:
        path=Path(arg)
        if arg.endswith('.json') and path.is_file():
            original=json.loads(path.read_text());bound=walk(original)
            if bound!=original:
                import hashlib
                content=json.dumps(bound,indent=2,sort_keys=True)+'\n'
                sha=hashlib.sha256(content.encode()).hexdigest()
                destination.mkdir(parents=True,exist_ok=True)
                target=destination/(path.stem+'-'+sha[:20]+'.json')
                if target.exists() and target.read_text()!=content:raise ValueError('Bound configuration changed')
                target.write_text(content)
                (destination/(target.stem+'.provenance.json')).write_text(json.dumps(dict(original=str(path),original_sha256=digest(path),bound_sha256=sha),indent=2)+'\n')
                arg=str(target)
        result.append(arg)
    return result
