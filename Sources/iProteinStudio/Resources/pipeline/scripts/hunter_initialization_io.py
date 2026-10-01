"""Engine-environment input preparation and audited Hunter seed handoff."""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import yaml
from hunter_stages import atomic, sha, value
from validate_prediction_geometry import inspect_geometry, read_pdb, read_cif


def run(command):
    subprocess.run([str(x) for x in command], check=True,
                   env=dict(os.environ, STUDIO_RFD3_AUDIT_RESUME='1',
                            PYTORCH_ENABLE_MPS_FALLBACK='0', TOKENIZERS_PARALLELISM='false'))


def template(spec):
    return yaml.safe_load(Path(value(spec['arguments'], '--template-yaml')).read_text())


def proteins(data):
    result = {}
    for entry in data['sequences']:
        if 'protein' not in entry: continue
        p = entry['protein']
        for chain in ([p['id']] if isinstance(p['id'], str) else p['id']):
            result[chain] = p['sequence']
    return result


def generate(spec, work, prepare_only=False):
    args = spec['arguments']; data = template(spec)
    root = Path(os.environ['NANOHUNTER_ROOT']); code = Path(os.environ.get('IPROTEINSTUDIO_PIPELINE_SNAPSHOT', Path(__file__).parents[1]))
    sys.path.insert(0, str(code / 'rfd3_scripts'))
    # runtime views also expose the same versioned app adapters here.
    if not (code / 'rfd3_scripts/prepare_campaign.py').is_file():
        sys.path.insert(0, str(root / 'rfd3_scripts'))
    import prepare_campaign as prep
    from rfd3_protein_campaign import design_cmd
    low, high = int(value(args, '--binder-min-len', '65')), int(value(args, '--binder-max-len', '100'))
    if low < 1 or high < low: raise ValueError('Invalid binder lengths.')
    sys.path.insert(0, str(code / 'scripts/nise'))
    from rfd3_initial import lengths as initial_lengths, atom_translation
    lengths = initial_lengths(dict(binder_min_len=low, binder_max_len=high,
                                   rfd3_num_bins=20, num_starts=spec['trajectories']))
    req = dict(design_mode='deNovo', design_name='hunter_initial', rfd3_root=str(root/'rfd3'),
               nanohunter_root=str(root), campaign_dir=str(work), conditions={},
               lengths=lengths, num_backbones=spec['trajectories'], top_n=spec['trajectories'],
               timesteps=200, recycles=2, batch_size=4, queues_per_bin=2, precision='bf16',
               seed_base=int(value(args,'--binder-random-seed',value(args,'--predictor-seed','42'))),
               is_non_loopy=True, sequences_per_backbone=1, sequence_model='solublempnn',
               run_affinity=False, run_apo=False, extra_predictors=[spec['refinement_engine']])
    targets = {k:v for k,v in proteins(data).items() if k != 'A'}
    ligands = [e['ligand'] for e in data['sequences'] if 'ligand' in e]
    if targets and ligands: raise ValueError('RFdiffusion3 starts currently accept a protein target or one small molecule, not both.')
    manifest = None
    if targets:
        from protein_structure import read_protein_atoms
        aa = dict(zip("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split(), "ARNDCQEGHILKMFPSTWYV"))
        target = value(args, '--initialization-target')
        if not target or not Path(target).is_file():
            raise ValueError('RFdiffusion3 needs the target structure. Select a PDB/CIF matching the target sequence.')
        atoms = read_protein_atoms(target)
        chains = {}
        for atom in atoms:
            chains.setdefault(atom.chain, {})[atom.residue_number] = atom.residue
        source_sequences = {c: ''.join(aa.get(n, 'X') for n in residues.values()) for c,residues in chains.items()}
        selected=[]
        for chain, sequence in targets.items():
            matches=[c for c,s in source_sequences.items() if s == sequence and c not in selected]
            if len(matches)!=1: raise ValueError('Target chain '+chain+' must match exactly one complete chain in the RFdiffusion3 target structure.')
            selected.append(matches[0])
        if list(targets) != [chr(66+i) for i in range(len(targets))]:
            raise ValueError('RFdiffusion3 starts require target chains B, C, … in sequence order; binder is A.')
        req.update(target_kind='protein', target_structure=target, target_chains=selected,
                   target_chain=','.join(selected), target_sequence=':'.join(targets.values()),binding_site_mode='surface_scan')
        sites=value(args,'--target-epitope-residues',' '.join(data.get('nanohunter',{}).get('target_epitope_residues',[])))
        if sites:
            import re
            for token in re.split(r'[,;\s]+',sites):
                if not token:continue
                m=re.fullmatch(r'([B-Z])(\d+)',token)
                if not m or m[1] not in targets:raise ValueError('RFdiffusion3 hotspots require chain-qualified residue positions, e.g. B45.')
                source=selected[list(targets).index(m[1])]; positions=list(chains[source])
                index=int(m[2])-1
                if not 0<=index<len(positions):raise ValueError('Hotspot is outside target sequence.')
                req['conditions'][source+str(positions[index])]=['hotspot']
            req['binding_site_mode']='targeted_epitope'
    elif len(ligands)==1 and ligands[0].get('smiles'):
        affinity = any('affinity' in p for p in data.get('properties', []))
        atom_helper = Path(prep.__file__).parent / 'boltz_ligand_atoms.py'
        result = subprocess.run([str(root/'venvs/NanoHunter_boltz/bin/python'), str(atom_helper),
                                 ligands[0]['smiles'], '1' if affinity else '0'],
                                check=True, capture_output=True, text=True)
        manifest = json.loads(result.stdout)
        if affinity and not manifest.get('standardized'):
            raise ValueError('Boltz affinity atom standardization failed; cannot map RFdiffusion3 atoms safely.')
        work.mkdir(parents=True, exist_ok=True)
        atomic(work/'ligand_manifest.json', manifest)
        req.update(target_kind='small_molecule',smiles=manifest['smiles_used'],ligand_source='smiles',component_id='LG1',sequence_model='lasermpnn')
    else:raise ValueError('RFdiffusion3 starts need target protein chains or one SMILES ligand.')
    request_path=work/'request.json';work.mkdir(parents=True,exist_ok=True)
    if request_path.exists() and json.loads(request_path.read_text()) != req:
        raise ValueError('RFdiffusion3 preparation settings changed.')
    atomic(request_path,req)
    if not (work/'config/campaign.json').exists():
        old_argv=sys.argv
        try:sys.argv=[str(Path(prep.__file__)),str(request_path)];prep.main()
        finally:sys.argv=old_argv
    cfg=json.loads((work/'config/campaign.json').read_text())
    if manifest:
        # Translate shared Boltz names through input-order correspondence, as in NISE.
        names=atom_translation(work/'assets/ligand',manifest)
        atomic(work/'atom_translation.json',names)
        inverse={v:k for k,v in names.items()}
        contacts=[]
        for constraint in data.get('constraints',[]):
            contacts.extend(p[1] for p in constraint.get('pocket',{}).get('contacts',[]) if len(p)==2)
        if contacts:
            design=Path(cfg['design_yaml']);d=yaml.safe_load(design.read_text())
            d[req['design_name']]['select_hotspots']={'LG1':','.join(inverse[n] for n in contacts)}
            design.write_text(yaml.safe_dump(d,sort_keys=False))
    if prepare_only: return
    for stage in ['fixtures','backbones']:
        print('NHSTEP|initialization||RFdiffusion3 '+stage,flush=True)
        command=design_cmd(cfg,root/'rfd3',work,stage)
        if cfg.get('ccd_mirror'):command+=['--ccd-mirror',cfg['ccd_mirror']]
        run(command)


def has_confidence(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {'iptm', 'i_ptm', 'iptm_score', 'ptm', 'complex_plddt', 'avg_plddt', 'mean_plddt', 'plddt', 'confidence_score'}:
                try:
                    if not isinstance(item, bool) and math.isfinite(float(item)): return True
                except (TypeError, ValueError): pass
            if has_confidence(item): return True
    elif isinstance(value, list):
        return any(has_confidence(item) for item in value)
    return False


def handoff(spec, source, output):
    count=spec['trajectories'];files={}
    rfd=spec['method']=='rfd3'
    paths=sorted((source/'rfd3/backbones').glob('design_*.pdb')) if rfd else []
    if rfd and len(paths)!=count:raise ValueError(f'Expected {count} backbones, received {len(paths)}.')
    for i in range(1,count+1):
        tag=f'run_{i:03d}';dest=output/tag/'cycle_00';dest.mkdir(parents=True,exist_ok=True)
        if rfd:
            data=copy.deepcopy(template(spec));structure=paths[i-1]
            residues=read_pdb(structure);n=sum('CA' in atoms for key,atoms in residues.items() if key[1]=='A')
            if n<1:raise ValueError('Generated backbone has no binder chain A.')
            data['sequences']=[e for e in data['sequences'] if 'protein' not in e or e['protein']['id']!='A']
            data['sequences'].insert(0,{'protein':dict(id='A',sequence='X'*n,msa='empty')})
            minimum=dest/'pred_min';minimum.mkdir(exist_ok=True)
            text=structure.read_text()
            mapping=source/'atom_translation.json'
            if mapping.exists():
                names=json.loads(mapping.read_text())
                text='\n'.join(line[:12]+names[line[12:16].strip()].rjust(4)+line[16:] if line.startswith('HETATM') and line[21]=='B' else line for line in text.splitlines())+'\n'
            (minimum/'model_0.pdb').write_text(text)
            for filename in [tag+'_cycle_00.yaml','boltz_input.yaml']:(dest/filename).write_text(yaml.safe_dump(data,sort_keys=False))
        else:
            original=source/tag/'cycle_00'
            candidates=[p for p in (original/'pred_min').glob('model_0.*') if p.suffix in {'.pdb','.cif'}]
            if len(candidates)!=1:raise ValueError('Incomplete or ambiguous cycle-00 structure: '+tag)
            input_path=original/(tag+'_cycle_00.yaml')
            if not input_path.exists():input_path=original/'boltz_input.yaml'
            data=yaml.safe_load(input_path.read_text())
            confidence = json.loads((original/'pred_min/confidence.json').read_text())
            if not has_confidence(confidence):
                raise ValueError('Starting predictor confidence is incomplete: ' + tag)
            shutil.copytree(original/'pred_min',dest/'pred_min',dirs_exist_ok=True)
            for filename in [tag+'_cycle_00.yaml','boltz_input.yaml']:shutil.copyfile(input_path,dest/filename)
        model=next(p for p in (dest/'pred_min').glob('model_0.*') if p.suffix in {'.pdb','.cif'})
        audit=inspect_geometry(model)
        if audit['errors']:raise ValueError('Invalid starting coordinates: '+str(audit['errors']))
        residues=read_pdb(model) if model.suffix=='.pdb' else read_cif(model)
        for chain,sequence in proteins(data).items():
            actual=sum('CA' in atoms for key,atoms in residues.items() if key[1]==chain)
            if actual!=len(sequence):raise ValueError(f'{tag}: chain {chain} coordinates ({actual}) do not match sequence ({len(sequence)}).')
        (dest/'pred_min/predictor.txt').write_text(spec['initial_engine']+'\n')
        for p in list((dest/'pred_min').glob('*'))+[dest/(tag+'_cycle_00.yaml'),dest/'boltz_input.yaml']:
            if p.is_file() and (p.name in {'model_0.pdb','model_0.cif','confidence.json','predictor.txt'} or p.suffix == '.yaml'):
                files[str(p.relative_to(output))]=sha(p)
    atomic(output/'initialization.json',dict(schema=1,status='complete',method=spec['method'],
           initial_engine=spec['initial_engine'],refinement_engine=spec['refinement_engine'],
           trajectories=count,files=files,completed_epoch=time.time(),cycle00_is_design=False,
           guidance_scope='Starting engine uses supported guidance; refinement applies only its supported guidance. ESMFold2 refinement is unrestrained.'))


def refinement_template(spec, destination):
    data = template(spec)
    engine = spec['refinement_engine']
    ligand_manifest = destination.parent / '_initialization/rfd3/ligand_manifest.json'
    if spec['method'] == 'rfd3' and ligand_manifest.is_file():
        for entry in data['sequences']:
            if 'ligand' in entry:
                entry['ligand']['smiles'] = json.loads(ligand_manifest.read_text())['smiles_used']
    if engine not in {'boltz', 'protenix-constraint-v0.5'}:
        for name in ['target_epitope_residues', 'epitope_residues']:
            data.get('nanohunter', {}).pop(name, None)
    if engine != 'boltz':
        data.pop('constraints', None)
        data.pop('properties', None)
    if engine not in {'boltz', 'protenix-v2', 'intellifold'}:
        data.pop('templates', None)
    original = Path(value(spec['arguments'], '--template-yaml')).parent
    for entry in data.get('sequences', []):
        protein = entry.get('protein', {})
        msa = protein.get('msa')
        if engine == 'esmfold2-fast-mlx' and protein:
            protein['msa'] = 'empty'
        elif msa and msa not in {'empty', 'auto'} and not Path(msa).is_absolute():
            protein['msa'] = str((original / msa).resolve())
    text = yaml.safe_dump(data, sort_keys=False)
    if destination.exists() and destination.read_text() != text:
        raise ValueError('Refinement template changed; create a new run.')
    destination.write_text(text)


if __name__=='__main__':
    mode,spec_path,source=sys.argv[1:];spec=json.loads(Path(spec_path).read_text())
    if mode in {'rfd3','prepare'}:generate(spec,Path(source),prepare_only=mode=='prepare')
    elif mode=='refinement-template':refinement_template(spec,Path(source))
    elif mode=='handoff':handoff(spec,Path(source),Path(spec_path).parent)
    else:raise ValueError('Unknown initialization operation')
