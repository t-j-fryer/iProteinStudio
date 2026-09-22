#!/usr/bin/env python3
"""Assemble a relocatable CPython closure on the release machine, never on clients.

Uses the interpreter's standalone distribution, not a copied virtualenv. Model
weights are excluded. Fails on external symlinks and unresolved editable installs.
This creates a local qualification artifact; signing/notarization is separate.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,shlex,configparser,re,ast
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--python',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--engine',required=True);p.add_argument('--imports',required=True);p.add_argument('--source',action='append',default=[]);p.add_argument('--standalone-python',type=Path);p.add_argument('--binary',action='append',default=[]);p.add_argument('--asset-mount',action='append',default=[]);p.add_argument('--runtime-link',action='append',default=[]);a=p.parse_args()
    probe='import sys,sysconfig,json;print(json.dumps(dict(base=sys.base_prefix,site=sysconfig.get_path("purelib"),version=sys.version.split()[0])))'
    info=json.loads(subprocess.check_output([str(a.python),'-I','-c',probe],text=True));base=Path(info['base']).resolve();site=Path(info['site'])
    if a.standalone_python:
        alternate=json.loads(subprocess.check_output([str(a.standalone_python),'-I','-c',probe],text=True))
        if alternate['version']!=info['version']:raise ValueError('Replacement standalone Python must match exact Python version')
        base=Path(alternate['base']).resolve()
    if 'cpython-' not in base.name or not (base/'lib').is_dir():raise ValueError('Require a pinned python-build-standalone interpreter, not system/framework Python')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def ignore(directory,names):
        return [n for n in names if n in ('__pycache__','.git','.venv','venv','.DS_Store') or n.endswith(('.pyc','.pt','.pth.tar','.ckpt','.safetensors','.bin')) or n=='site-packages']
    shutil.copytree(base,out/'python',symlinks=True,ignore=ignore)
    dest=out/'python/lib'/('python'+'.'.join(info['version'].split('.')[:2]))/'site-packages'
    shutil.copytree(site,dest,symlinks=True,ignore=lambda d,n:[x for x in n if x in ('__pycache__','.DS_Store') or x.endswith(('.pyc','.pt','.ckpt','.safetensors'))])
    for value in a.source:
        name,path=value.split('=',1)
        if '/' in name or name in ('.','..'):raise ValueError('Unsafe source name')
        shutil.copytree(path,out/'sources'/name,symlinks=True,ignore=ignore)
        # LASErMPNN's fixed chemical tables are serialized tensors, not model
        # checkpoints. Its imports require these exact upstream data files.
        if name=='LASErMPNN':
            for table in ('new_ideal_coords.pt','new_ideal_bond_lengths.pt','new_ideal_bond_angles.pt','rotamer_alignment.pt','ideal_aa_coords_prot.pt','ligandmpnn_training_pdb_codes.pt','ligandmpnn_validation_pdb_codes.pt','ligandmpnn_test_sm_pdb_codes.pt'):
                target=out/'sources'/name/'files'/table
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(Path(path)/'files'/table,target)
    asset_mounts=dict(v.split('=',1) for v in a.asset_mount)
    runtime_links=dict(v.split('=',1) for v in a.runtime_link)
    for name,legacy in asset_mounts.items():
        if any(Path(v).is_absolute() or '..' in Path(v).parts for v in (name,legacy)):raise ValueError('Unsafe asset mount')
        target=out/name
        if target.is_symlink() or target.is_file():target.unlink()
        elif target.is_dir():shutil.rmtree(target)
    for name,relative in runtime_links.items():
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
        if out not in (target.parent/relative).resolve().parents:raise ValueError('Unsafe runtime link')
        target.symlink_to(relative)
    # Freeze editable packages into ordinary package files, recording exact bytes.
    # Read setuptools' literal mapping without executing an untrusted finder.
    editable=[]
    for path in dest.glob('*.pth'):
        text=path.read_text()
        if '__editable__' in text:
            match=re.fullmatch(r'import ([A-Za-z0-9_]+); \1.install\(\)\s*',text)
            if not match:raise ValueError('Unsupported editable loader: '+str(path))
            finder=dest/(match[1]+'.py');mapping=None
            for node in ast.parse(finder.read_text()).body:
                if isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) and node.target.id=='MAPPING':mapping=ast.literal_eval(node.value)
            if not mapping:raise ValueError('Missing editable package mapping')
            for name,source in mapping.items():
                if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Unsupported editable namespace')
                source=Path(source);target=dest/name
                if target.exists():
                    if name=='tests':
                        editable.append('tests: retained existing import precedence');continue
                    raise ValueError('Editable package collision: '+name)
                if source.is_dir():shutil.copytree(source,target,symlinks=True,ignore=ignore)
                elif source.with_suffix('.py').is_file():shutil.copy2(source.with_suffix('.py'),target.with_suffix('.py'))
                else:raise ValueError('Missing editable source: '+str(source))
                editable.append(name)
            finder.unlink();path.unlink()
        elif any(line.startswith('/') for line in text.splitlines()):raise ValueError('Unresolved absolute path file: '+str(path))
    for value in a.binary:
        name,source=value.split('=',1)
        if not re.fullmatch('[A-Za-z0-9_.-]+',name):raise ValueError('Unsafe binary name')
        shutil.copy2(source,out/'python/bin'/name)
    for path in out.rglob('*'):
        if path.is_symlink() and (out not in path.resolve().parents or not path.exists()):raise ValueError('External/broken symlink: '+str(path))
    # Native dependencies must be package-relative or Apple system libraries.
    native=[];minimum_macos=[]
    for path in out.rglob('*'):
        if not path.is_file() or path.is_symlink():continue
        with path.open('rb') as f:magic=f.read(4)
        if magic not in (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe'):continue
        listing=subprocess.check_output(['/usr/bin/otool','-L',str(path)],text=True)
        identifiers={line.strip() for line in subprocess.check_output(['/usr/bin/otool','-D',str(path)],text=True).splitlines()[1:]}
        changed=False
        commands=subprocess.check_output(['/usr/bin/otool','-l',str(path)],text=True)
        minimum_macos += re.findall(r'\bminos\s+(\d+\.\d+(?:\.\d+)?)',commands)
        for rpath in set(re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.+?) \(offset',commands)):
            if rpath.startswith('/') and not rpath.startswith(('/usr/lib','/System/Library')):
                subprocess.run(['/usr/bin/install_name_tool','-delete_rpath',rpath,str(path)],check=True,capture_output=True);changed=True
        for line in listing.splitlines()[1:]:
            dep=line.strip().split(' (')[0]
            if dep==str(path) or dep in identifiers:
                subprocess.run(['/usr/bin/install_name_tool','-id','@rpath/'+path.name,str(path)],check=True,capture_output=True)
                changed=True;continue
            if dep.startswith(str(base)+'/'):
                target=out/'python'/Path(dep).relative_to(base)
                if not target.is_file():raise ValueError('Missing internal native dependency: '+dep)
                relative='@loader_path/'+os.path.relpath(target,path.parent)
                if target==path:subprocess.run(['/usr/bin/install_name_tool','-id','@rpath/'+path.name,str(path)],check=True,capture_output=True)
                else:subprocess.run(['/usr/bin/install_name_tool','-change',dep,relative,str(path)],check=True,capture_output=True)
                changed=True;continue
            if dep.startswith('/') and not dep.startswith(('/usr/lib/','/System/Library/')):raise ValueError('External Mach-O dependency: '+dep+' in '+str(path))
        if changed:subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(path)],check=True,capture_output=True)
        native.append(str(path.relative_to(out)))
    # Rebuild console launchers with a relative interpreter; never copy venv shebangs.
    for entry in dest.glob('*.dist-info/entry_points.txt'):
        cfg=configparser.ConfigParser();cfg.optionxform=str;cfg.read(entry)
        if not cfg.has_section('console_scripts'):continue
        for name,target in cfg.items('console_scripts'):
            if not re.fullmatch('[A-Za-z0-9_.-]+',name):raise ValueError('Unsafe console entrypoint')
            module,attribute=target.split('[',1)[0].strip().split(':',1)
            code='import importlib,sys; f=importlib.import_module('+repr(module)+'); '+ '; '.join('f=getattr(f,'+repr(v)+')' for v in attribute.split('.'))+'; sys.exit(f())'
            launcher=out/'python/bin'/name
            if launcher.is_symlink():launcher.unlink()
            launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/python3" -c '+shlex.quote(code)+' "$@"\n');launcher.chmod(0o755)
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')};env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    from relocate_python_metadata import relocate
    relocate(out/"python")
    # Force real relocation, including a space and Unicode, before recording success.
    relocated=out.with_name(out.name+' relocation Ω');out.rename(relocated)
    try:
        executable=relocated/'python/bin/python3'
        check='import importlib,json,sys; '+ '; '.join('importlib.import_module('+repr(n)+')' for n in a.imports.split(','))+'; print(json.dumps(dict(executable=sys.executable,version=sys.version)))'
        try:result=subprocess.check_output([str(executable),'-I','-B','-c',check],env=env,text=True,stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(e.output,file=sys.stderr);raise
    finally:relocated.rename(out)
    inventory={str(p.relative_to(out)):(dict(symlink=os.readlink(p)) if p.is_symlink() else dict(sha256=sha(p),size=p.stat().st_size)) for p in out.rglob('*') if p.is_file() or p.is_symlink()}
    static_data_files=[name for name in inventory if name.startswith('sources/LASErMPNN/files/') and name.endswith('.pt')]
    manifest=dict(static_data_files=static_data_files,schema_version=1,engine=a.engine,python=info['version'],files=inventory,asset_mounts=asset_mounts,native_files=native,vendored_editables=editable,relocation_imports=a.imports.split(','),relocation_result=json.dumps(dict(version=info['version'],passed=True,path_with_spaces_and_unicode=True)),channel='trusted-beta',signed=False,notarized=False,contains_weights=False,minimum_macos=max(minimum_macos,key=lambda v:tuple(map(int,v.split('.')))) if minimum_macos else None,architecture='arm64')
    (out/'runtime.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),files=len(inventory),bytes=sum(v.get('size',0) for v in inventory.values()),manifest_sha256=sha(out/'runtime.json'))))

if __name__=='__main__':main()
