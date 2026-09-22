"""Immutable portable-runtime bindings for queued/resumed jobs.

Legacy environments are explicitly recorded as legacy; they are not claimed to
be portable or exactly preserved. Packages are never garbage-collected while a
plan references them. Model assets retain the workflow's existing hash contract.
"""
import json,os
from pathlib import Path
from .common import StudioError,file_digest,atomic_json,runtime_root

def capture(root=None,provenance=None,normalized=None):
    root=Path(root or runtime_root());result={}
    for pointer in sorted((root/'components').glob('*/current')):
        manifest=pointer/'runtime.json'
        if not manifest.is_file():continue
        record=json.loads(manifest.read_text());component=pointer.parent.name
        if provenance is not None and component != 'control':
            tokens=[]
            def visit(value):
                if isinstance(value,str):tokens.append(value)
                elif isinstance(value,dict):
                    for v in value.values():visit(v)
                elif isinstance(value,list):
                    for v in value:visit(v)
            visit(normalized)
            tokens += [v.get('path','') for v in provenance]
            registry=Path(__file__).resolve().parents[2]/'scripts/engine_registry.json'
            descriptors=json.loads(registry.read_text())['engines'] if registry.is_file() else {}
            names={name for name,d in descriptors.items() if d['component']==component}|{component}
            names.update(alias for d in descriptors.values() if d['component']==component for alias in d.get('aliases',[]))
            roots=[str(pointer.parent),str(pointer.resolve())]
            roots += [str(root/name) for d in descriptors.values() if d['component']==component for name in d.get('mappings',{})]
            if not any(v.lower() in names or any(v==r or v.startswith(r+'/') for r in roots) for v in tokens):continue
        if record.get('engine')!=component or record.get('schema_version')!=1:raise StudioError('Invalid portable runtime identity: '+component)
        result[component]=dict(path=str(pointer.resolve()),manifest_sha256=file_digest(manifest))
    return result

def retain(plan,root=None):
    root=Path(root or runtime_root())
    for component,binding in plan.get('runtime_bindings',{}).items():
        atomic_json(root/'runtime_pins'/component/(plan['id']+'.json'),dict(plan_id=plan['id'],plan_sha256=plan['sha256'],**binding))

def verify(bindings):
    if not bindings: return
    # Validate the complete closure, including symlink identity, before inference.
    import importlib.util
    bridge=Path(__file__).resolve().parents[1]
    scripts=bridge/'runtime_support'
    if not scripts.is_dir():scripts=bridge.parent/'scripts'
    import sys
    sys.path.insert(0,str(scripts))
    try:
        from runtime_package import verify as verify_package
        for component,binding in bindings.items():
            try:verify_package(Path(binding['path']),binding['manifest_sha256'],component)
            except (OSError,ValueError,KeyError) as e:raise StudioError('Pinned '+component+' runtime is missing or changed. Restore it to resume this job: '+str(e)) from e
    finally:sys.path.remove(str(scripts))

def environment(bindings):
    # -B prevents writes, but does not prevent loading existing .pyc files.
    # A non-directory prefix makes CPython use verified source on every import.
    return {'IPROTEINSTUDIO_RUNTIME_BINDINGS':json.dumps(bindings,sort_keys=True),'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':'/dev/null'}
