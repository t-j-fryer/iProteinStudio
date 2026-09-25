"""Portable, data-only Phase-0 cycle01 cohort; never imports affinity decisions.

Archives are unpacked by the user. Paths are relative, symlinks forbidden, and
RDKit molecules travel as native binary data inside JSON, never Python pickle.
"""
import base64
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import pickle
import re
import shutil
import zipfile

FORMAT = 'iproteinstudio-nise-cohort'
BOUNDARY = 'phase0.cycle01.after_geometry.before_affinity'
LOCKED = ('smiles', 'seed', 'hotspot_atoms', 'exposed_atoms', 'hotspot_distance',
          'exposure_min_fraction', 'exposure_mode', 'ligand_atom_signature',
          'ligand_atoms_generated_for')
AA = dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(), 'ARNDCQEGHILKMFPSTWYV'))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.part')
    temp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n');temp.replace(path)


def safe(root, relative):
    root=Path(root).resolve()
    if not isinstance(relative,str) or '\\' in relative: raise ValueError('Invalid cohort path')
    parts=PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or any(p in ('.','..') for p in parts.parts): raise ValueError('Unsafe cohort path')
    path=root
    for part in parts.parts:
        path=path/part
        if path.is_symlink(): raise ValueError('Cohort symlinks are not allowed')
    if root not in path.resolve().parents: raise ValueError('Cohort path escapes package')
    return path


def audit_pdb(path, sequence, atom_map):
    residues={};ligand={};models=0
    for line in path.read_text().splitlines():
        if line.startswith('MODEL'): models+=1
        if not line.startswith(('ATOM  ','HETATM')): continue
        if len(line)<78 or line[16] not in (' ','A'): raise ValueError('Invalid/alternate structure atom')
        xyz=[float(line[s:s+8]) for s in (30,38,46)]
        if not all(math.isfinite(x) for x in xyz): raise ValueError('Non-finite structure coordinates')
        atom=line[12:16].strip();chain=line[21];element=line[76:78].strip()
        if chain=='A' and line.startswith('ATOM  '):
            key=line[22:27];res=residues.setdefault(key,{'name':line[17:20],'atoms':set()})
            if atom in res['atoms']:raise ValueError('Duplicate protein atom')
            res['atoms'].add(atom)
        elif chain=='B' and element not in ('H','D'):
            if atom in ligand:raise ValueError('Duplicate ligand atom')
            ligand[atom]=element
        elif element not in ('H','D'): raise ValueError('Unexpected chain in cohort structure')
    if models>1 or ''.join(AA.get(r['name'],'?') for r in residues.values())!=sequence:raise ValueError('Cohort protein sequence mismatch')
    if not all({'N','CA','C','O'}<=r['atoms'] for r in residues.values()):raise ValueError('Incomplete backbone')
    expected={a['name']:a['el'].upper() for a in atom_map['atoms']}
    if ligand!=expected:raise ValueError('Ligand atom identity mismatch')


class MoleculeOnlyUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module,name)==('rdkit.Chem.rdchem','Mol'):
            from rdkit.Chem.rdchem import Mol
            return Mol
        raise ValueError('Unsupported object in source molecule cache')


def molecule_json(path):
    from rdkit import Chem
    mols=MoleculeOnlyUnpickler(io.BytesIO(path.read_bytes())).load()
    if not isinstance(mols,dict) or any(not isinstance(k,str) or not isinstance(m,Chem.Mol) for k,m in mols.items()):raise ValueError('Invalid source molecule cache')
    return {k:base64.b64encode(m.ToBinary(Chem.PropertyPickleOptions.AllProps)).decode() for k,m in mols.items()}


def restore_molecules(path, destination):
    from rdkit import Chem
    values=json.loads(path.read_text());mols={}
    if not isinstance(values,dict) or not 1<=len(values)<=16:raise ValueError('Invalid portable molecule cache')
    for k,v in values.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+',k) or not isinstance(v,str) or len(v)>2_000_000:raise ValueError('Invalid portable molecule')
        mol=Chem.Mol(base64.b64decode(v,validate=True))
        if mol is None or not 1<=mol.GetNumAtoms()<=1000 or mol.GetNumConformers()!=1:raise ValueError('Invalid ligand conformer')
        mols[k]=mol
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(pickle.dumps(mols))


def portable_npz(source, destination):
    """Export trusted local Boltz data, replacing its object-valued null pocket."""
    import numpy as np
    with np.load(source, allow_pickle=True) as loaded:
        arrays = {key: loaded[key] for key in loaded.files}
    for key, value in list(arrays.items()):
        if value.dtype.hasobject:
            if key != 'pocket' or value.shape != () or value.item() is not None:
                raise ValueError('Unsupported object array in source cache')
            del arrays[key]
            arrays['_studio_null_pocket'] = np.array(1, dtype=np.uint8)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination, **arrays)


def restore_npz(source, destination):
    import numpy as np
    with zipfile.ZipFile(source) as archive:
        if sum(i.file_size for i in archive.infolist()) > 200_000_000:
            raise ValueError('Oversized numeric cache')
    with np.load(source, allow_pickle=False) as loaded:
        arrays = {key: loaded[key] for key in loaded.files}
    marker = arrays.pop('_studio_null_pocket', None)
    if marker is not None:
        if marker.shape != () or marker.dtype != np.uint8 or marker.item() != 1 or 'pocket' in arrays:
            raise ValueError('Invalid portable pocket marker')
        arrays['pocket'] = np.array(None, dtype=object)
    np.savez_compressed(destination, **arrays)


def validate(root, settings=None):
    root=Path(root)
    if root.is_symlink():raise ValueError('Cohort root cannot be a symlink')
    data=json.loads(safe(root,'cohort.json').read_text())
    if data.get('format')!=FORMAT or data.get('schema')!=1 or data.get('boundary')!=BOUNDARY:raise ValueError('Unsupported NISE cohort boundary')
    entries=data['candidates'];files=data['files'];names=set();origins=set()
    if not 1<=len(entries)<=30000 or len(files)>600000:raise ValueError('Invalid cohort size')
    if settings is not None:
        for key in LOCKED:
            if settings.get(key)!=data['request'].get(key):raise ValueError('Imported cohort changes saved ligand/geometry setting: '+key)
        if not settings['phase0_nesso_screen'] or not settings['selective_affinity'] or settings['phase0_refine_cycles']<1:raise ValueError('Cohort requires initial screening, selective affinity and at least one refinement round')
        if settings['backbone_method']!='protein-hunter':raise ValueError('Imported cohort replaces backbone generation; retain its Protein Hunter origin')
    for relative,checksum in files.items():
        path=safe(root,relative)
        if path.suffix=='.pkl' or not re.fullmatch(r'[0-9a-f]{64}',checksum) or not path.is_file() or path.stat().st_size>200_000_000 or sha(path)!=checksum:raise ValueError('Cohort artifact missing, unsafe or changed: '+relative)
    for required in ('ligand_atom_map.json', 'ligand.yaml', 'sequences.fasta', 'candidates.csv'):
        if required not in files:raise ValueError('Missing cohort metadata: '+required)
    atom_map=json.loads(safe(root,'ligand_atom_map.json').read_text())
    for entry in entries:
        name=entry['name'];origin=entry['origin'];seq=entry['sequence']
        if not re.fullmatch(r'L\d+_c1_\d+',name) or origin!=name.split('_')[0] or name in names:raise ValueError('Invalid/duplicate cohort identity')
        if not re.fullmatch(r'[ACDEFGHIKLMNPQRSTVWY]{1,700}',seq):raise ValueError('Invalid cohort sequence')
        names.add(name);origins.add(origin)
        operation=entry['operation'];pred=operation['result']['prediction'];spec=operation['input']
        if (spec.get('phase')!='structure' or spec['sequence']!=seq or spec['smiles']!=atom_map['smiles_used'] or pred.get('pbind') is not None or pred['name']!=name):raise ValueError('Cohort contains incompatible prediction or affinity state')
        if not math.isfinite(pred['ligand_plddt']) or not 0<=pred['ligand_plddt']<=100:raise ValueError('Invalid ligand confidence')
        if entry['geometry'].get('passed') is not True:raise ValueError('Cohort contains a geometry failure')
        if entry['ref_pdb'] != f'phase0/cycle00/{origin}_ref.pdb':raise ValueError('Invalid parent reference path')
        expected_pocket=dict(binder='A', contacts=[['B', atom] for atom in data['request']['hotspot_atoms']],
                             force=True, max_distance=data['request']['hotspot_distance'])
        if (spec.get('seed')!=data['request']['seed'] or spec.get('pocket')!=expected_pocket
                or spec.get('potentials') is not True or spec.get('affinity') is not True):
            raise ValueError('Imported folding specification does not match cohort settings')
        for relative in entry['artifacts']+[entry['ref_pdb']]:
            if relative not in files:raise ValueError('Untracked candidate artifact')
        if pred['pdb'] not in entry['artifacts']:raise ValueError('Untracked candidate structure')
        audit_pdb(safe(root,pred['pdb']),seq,atom_map)
        base=f'phase0/cycle01/fold/{name}/'
        if any(not x.startswith(base) for x in entry['artifacts']):raise ValueError('Candidate artifact escapes operation')
        required=[base+f'yaml/{name}.yaml',base+f'out/boltz_results_yaml/predictions/{name}/pre_affinity_{name}.npz',base+f'out/boltz_results_yaml/processed/mols/{name}.molecule.json']
        if not set(required)<=set(entry['artifacts']):raise ValueError('Missing structure/affinity cache')
    if len(entries)!=data['candidate_count'] or len(origins)!=data['lineage_count']:raise ValueError('Cohort counts disagree')
    if settings and settings['trajectories']>len(origins):raise ValueError('More trajectories requested than imported lineages')
    return data,[safe(root,p) for p in files]+[safe(root,'cohort.json')]


def export(source, output):
    source=Path(source).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    request=json.loads((source/'nise_config.json').read_text())['request']
    entries=[];hashes={};origins=set()
    def copy_file(path,relative,expected=None):
        checksum=sha(path)
        if expected is not None and checksum!=expected:raise ValueError('Source checkpoint artifact changed: '+str(path))
        target=safe(output,relative);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);hashes[relative]=checksum
    copy_file(source/'ligand_atom_map.json','ligand_atom_map.json')
    copy_file(source/'ligand.yaml','ligand.yaml')
    for f in sorted((source/'candidates').glob('L*_c1_*.json')):
        c=json.loads(f.read_text())
        if c.get('geometry_passed') is not True:continue
        name=c['name'];origin=name.split('_')[0];origins.add(origin)
        receipt=source/f'phase0/cycle01/fold/{name}/completed.json';operation=json.loads(receipt.read_text())
        artifacts=[]
        for relative,checksum in operation['files'].items():
            path=safe(source,relative)
            if sha(path)!=checksum:raise ValueError('Changed source operation artifact')
            if 'affinity_' in path.name and not path.name.startswith('pre_affinity_'):raise ValueError('Affinity output in structure receipt')
            if path.suffix=='.pkl':
                relative=relative.removesuffix('.pkl')+'.molecule.json';target=safe(output,relative);write(target,molecule_json(path));hashes[relative]=sha(target)
            elif path.suffix=='.npz':
                target=safe(output,relative);portable_npz(path,target);hashes[relative]=sha(target)
            else:copy_file(path,relative,checksum)
            artifacts.append(relative)
        pred=dict(operation['result']['prediction']);pred['pdb']=str(Path(pred['pdb']).resolve().relative_to(source));pred['pbind']=None
        ref=str(Path(c['ref_pdb']))
        if Path(ref).is_absolute():ref=str(Path(ref).resolve().relative_to(source))
        copy_file(safe(source,ref),ref)
        entries.append(dict(name=name,origin=origin,sequence=c['sequence'],ref_pdb=ref,geometry=c['atom_checks'],
            ca_rmsd=c['ca_rmsd'],ligand_rmsd=c['ligand_rmsd'],artifacts=artifacts,
            source_receipt_sha256=sha(receipt),operation=dict(input=operation['input'],result=dict(prediction=pred))))
    if not entries:raise ValueError('No eligible first-refinement candidates')
    with (output/'sequences.fasta').open('w') as f:
        for e in entries:f.write(f">{e['name']} origin={e['origin']}\n{e['sequence']}\n")
    with (output/'candidates.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['name','origin','sequence','pdb','ligand_plddt','geometry_passed','affinity_used_for_selection'])
        for e in entries:w.writerow([e['name'],e['origin'],e['sequence'],e['operation']['result']['prediction']['pdb'],e['operation']['result']['prediction']['ligand_plddt'],True,False])
    for name in ['sequences.fasta','candidates.csv']:hashes[name]=sha(output/name)
    # Suggestions retain source chemistry/filtering; no old scored ranking enters the new run.
    request.update(screening_engine='nesso',phase0_nesso_screen=True,nesso_screen=True)
    manifest=dict(format=FORMAT,schema=1,boundary=BOUNDARY,candidate_count=len(entries),lineage_count=len(origins),
        source_run=source.name,source_config_sha256=sha(source/'nise_config.json'),request=request,
        candidates=entries,files=hashes,affinity_selection_imported=False)
    if (source/'studio_job.json').exists():
        manifest['source_job']=json.loads((source/'studio_job.json').read_text())
    write(output/'cohort.json',manifest);validate(output)
    return manifest


def validate_import(output, config):
    descriptor=config.get('cohort')
    if not isinstance(descriptor,dict) or set(descriptor)!={'path','sha256'} or descriptor['path']!='cohort':raise ValueError('Invalid cohort import descriptor')
    root=Path(output)/'cohort'
    if sha(safe(root,'cohort.json'))!=descriptor['sha256']:raise ValueError('Imported cohort manifest changed')
    return validate(root,config['request'])


def materialize(output, config):
    """Build local native structure receipts; safe to replay after interruption."""
    from runtime import Journal
    output=Path(output);data,_=validate_import(output,config);root=output/'cohort';journal=Journal(output)
    for entry in data['candidates']:
        name=entry['name'];receipt=output/f'phase0/cycle01/fold/{name}/completed.json';operation=entry['operation'];spec=operation['input']
        if receipt.exists():
            journal.load(receipt,spec)
            if sha(safe(output,entry['ref_pdb']))!=data['files'][entry['ref_pdb']]:raise ValueError('Imported parent reference changed')
            continue
        paths=[]
        for relative in entry['artifacts']:
            src=safe(root,relative);target=safe(output,relative);target.parent.mkdir(parents=True,exist_ok=True)
            if relative.endswith('.molecule.json'):
                target=Path(str(target).removesuffix('.molecule.json')+'.pkl');restore_molecules(src,target)
            elif src.suffix=='.npz':
                restore_npz(src,target)
            else:
                shutil.copyfile(src,target)
            paths.append(target)
        ref=safe(output,entry['ref_pdb']);ref.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(safe(root,entry['ref_pdb']),ref)
        result=json.loads(json.dumps(operation['result']));result['prediction']['pdb']=str(safe(output,result['prediction']['pdb']))
        result['import_provenance']=dict(cohort_sha256=config['cohort']['sha256'],source_receipt_sha256=entry['source_receipt_sha256'])
        journal.save(receipt,spec,result,paths)
    return data['candidates']


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    ex=sub.add_parser('export');ex.add_argument('source',type=Path);ex.add_argument('output',type=Path)
    ve=sub.add_parser('verify');ve.add_argument('package',type=Path)
    args=p.parse_args()
    d=export(args.source,args.output) if args.command=='export' else validate(args.package)[0]
    print(f"Verified {d['candidate_count']} candidates across {d['lineage_count']} lineages.")
