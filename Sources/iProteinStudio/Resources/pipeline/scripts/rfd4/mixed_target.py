"""Lossless, explicit small-molecule context for protein-target search.

Native authoring uses AtomWorks/Biotite chemistry, never distance-inferred bonds.
Prediction uses the same SMILES state on every cycle. Atom names are translated
by the pinned parsers' input-order rules, never by nearest-coordinate matching.
"""
import json
import math
from collections import Counter
from pathlib import Path
from .contract import atomic, sha


def ligand_mask(atoms):
    import biotite.structure as bs
    if bs.filter_nucleotides(atoms).any():
        raise ValueError('Protein-target search does not support nucleic-acid context.')
    return ~(bs.filter_amino_acids(atoms) | bs.filter_solvent(atoms))


def molecule_record(atoms, source_id, chain, component):
    from biotite.interface.rdkit import to_mol
    from rdkit import Chem, rdBase
    import numpy as np
    atoms = atoms[~np.isin(atoms.element, ['H', 'D'])]
    if not len(atoms) or not np.isfinite(atoms.coord).all():
        raise ValueError('Ligand has missing/nonfinite heavy-atom coordinates: ' + source_id)
    names = list(map(str, atoms.atom_name))
    if len(set(names)) != len(names): raise ValueError('Duplicate ligand atom names: ' + source_id)
    if len(atoms) > 1 and (atoms.bonds is None or not atoms.bonds.get_bond_count()):
        raise ValueError('Ligand needs explicit chemical connectivity: ' + source_id)
    mol = to_mol(atoms, explicit_hydrogen=False)
    Chem.SanitizeMol(mol)
    Chem.AssignStereochemistryFrom3D(mol)
    if mol.GetNumAtoms() != len(atoms) or len(Chem.GetMolFrags(mol)) != 1:
        raise ValueError('Each retained ligand must be one complete, connected molecule: ' + source_id)
    if [a.GetSymbol().upper() for a in mol.GetAtoms()] != [str(e).upper() for e in atoms.element]:
        raise ValueError('Native chemistry conversion changed atom order or elements.')
    canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
    # Carry source identity through SMILES traversal explicitly, including
    # symmetric atoms; a substructure match cannot establish that correspondence.
    for a in mol.GetAtoms(): a.SetAtomMapNum(a.GetIdx()+1)
    traversed = Chem.MolFromSmiles(Chem.MolToSmiles(mol, isomericSmiles=True))
    source_indices = [a.GetAtomMapNum()-1 for a in traversed.GetAtoms()]
    for a in traversed.GetAtoms(): a.SetAtomMapNum(0)
    smiles = Chem.MolToSmiles(traversed, canonical=False, isomericSmiles=True)
    order = json.loads(traversed.GetProp('_smilesAtomOutputOrder'))
    source_order = [source_indices[i] for i in order]
    parsed = Chem.MolFromSmiles(smiles)
    if Chem.MolToSmiles(parsed, isomericSmiles=True) != canonical:
        raise ValueError('Ligand SMILES round trip changed chemical state.')
    records = [dict(index=i, name=names[j], element=parsed.GetAtomWithIdx(i).GetSymbol().upper(),
                    charge=parsed.GetAtomWithIdx(i).GetFormalCharge(),
                    xyz=list(map(float, atoms.coord[j]))) for i,j in enumerate(source_order)]
    bonds = [dict(a=records[b.GetBeginAtomIdx()]['name'], b=records[b.GetEndAtomIdx()]['name'],
                  order=str(b.GetBondType()), stereo=str(b.GetStereo())) for b in parsed.GetBonds()]
    return dict(source_id=source_id, source_component=str(atoms.res_name[0]),
                chain=chain, component=component, residue=1, smiles=smiles,
                canonical_smiles=canonical, formal_charge=Chem.GetFormalCharge(parsed),
                atoms=records, bonds=bonds, rdkit_version=rdBase.rdkitVersion,
                chemical_state='Explicit source graph/charge; stereochemistry assigned from source coordinates; no standardization')


def prepare_target(atoms, cfg, destination):
    """Return a canonical target assembly, or None for unchanged protein-only input."""
    import numpy as np
    import biotite.structure as bs
    from .targets import selected_chains, hotspot_map
    nonprotein = ligand_mask(atoms)
    if not nonprotein.any():
        if cfg.get('target_ligand_ids'): raise ValueError('Requested ligands are absent from the target.')
        return None
    protein = bs.filter_amino_acids(atoms)
    chains = selected_chains(atoms.chain_id[protein], cfg['source_target_chain'])
    hot = hotspot_map(cfg, chains)
    keys = list(dict.fromkeys((str(c),int(r),str(i),str(n)) for c,r,i,n in
                            zip(atoms.chain_id[nonprotein],atoms.res_id[nonprotein],atoms.ins_code[nonprotein],atoms.res_name[nonprotein])))
    labels = [f'{c}:{r}{i.strip()}:{n}' for c,r,i,n in keys]
    selected = cfg.get('target_ligand_ids') or labels
    if len(set(selected)) != len(selected) or any(k not in labels for k in selected):
        raise ValueError('Choose ligand instances present in the source: ' + ', '.join(labels))
    if len(chains)+len(selected)>25: raise ValueError('Protein and ligand context together must fit target chains B–Z.')
    parts=[]; identities=[]; mapped_hot=[]; ligands=[]; target_ca={}
    from biotite.sequence import ProteinSequence
    for i,c in enumerate(chains):
        part=atoms[protein & (atoms.chain_id==c)].copy();out=chr(66+i)
        _,names=bs.get_residues(part)
        identities.append(dict(source_chain=c,native_chain=out,output_chain=out,
                               sequence=''.join(ProteinSequence.convert_letter_3to1(n) for n in names)))
        target_ca[out]=part.coord[part.atom_name=='CA'].tolist()
        part.chain_id[:]=out;parts.append(part)
        mapped_hot.extend(out+':'+str(n) for n in hot[c])
    for i,label in enumerate(selected):
        c,r,ins,n=keys[labels.index(label)]
        mask=nonprotein & (atoms.chain_id==c) & (atoms.res_id==r) & (atoms.ins_code==ins) & (atoms.res_name==n)
        if atoms.bonds is not None:
            for a,b,_ in atoms.bonds.as_array():
                if bool(mask[a]) != bool(mask[b]):
                    raise ValueError('Covalently connected ligand components need an explicit bonded-assembly workflow: '+label)
        part=atoms[mask].copy();chain=chr(66+len(chains)+i);component='L;'+ '0123456789ABCDEFGHIJKLMNOP'[i]
        record=molecule_record(part,label,chain,component);ligands.append(record)
        part=part[~np.isin(part.element,['H','D'])]
        part.chain_id[:]=chain;part.res_id[:]=1;part.ins_code[:]='';part.res_name[:]=component
        parts.append(part)
    combined=parts[0]
    for part in parts[1:]:combined=combined+part
    manifest=dict(schema=1,source_sha256=sha(cfg['source']),ligands=ligands,target_ca=target_ca,
                  omitted_by_explicit_selection=[k for k in labels if k not in selected],
                  protein_chains=[r['output_chain'] for r in identities])
    validate_predictor(dict(settings=cfg,target_ligands=manifest))
    atomic(Path(destination)/'target_ligands.json',manifest)
    atomic(Path(destination)/'target_identity.json',dict(chains=identities))
    return combined,manifest,mapped_hot


def write_components(path, manifest):
    """Embed the exact retained graphs in a CIF, including custom components."""
    import gemmi
    doc=gemmi.cif.read_file(str(path));block=doc.sole_block()
    saved={prefix:block.get_mmcif_category(prefix) for prefix in ('_chem_comp.','_chem_comp_atom.','_chem_comp_bond.')}
    from rdkit import Chem
    added={prefix:[] for prefix in saved};seen={}
    for ligand in manifest['ligands']:
        name=ligand['component'];mol=Chem.MolFromSmiles(ligand['smiles'])
        signature=(ligand['canonical_smiles'],tuple((a['name'],a['element']) for a in ligand['atoms']))
        if name in seen:
            if seen[name]!=signature:raise ValueError('Conflicting chemical definitions for component '+name)
            continue
        seen[name]=signature
        added['_chem_comp.'].append(dict(id=name,type='non-polymer',name=ligand['source_component']))
        for atom in ligand['atoms']:
            row=dict(comp_id=name,atom_id=atom['name'],type_symbol=atom['element'],charge=str(atom['charge']),
                     pdbx_aromatic_flag='Y' if mol.GetAtomWithIdx(atom['index']).GetIsAromatic() else 'N',pdbx_leaving_atom_flag='N')
            row.update({f'pdbx_model_Cartn_{axis}_ideal':str(v) for axis,v in zip('xyz',atom['xyz'])})
            added['_chem_comp_atom.'].append(row)
        for bond in ligand['bonds']:
            order={'SINGLE':'SING','DOUBLE':'DOUB','TRIPLE':'TRIP','AROMATIC':'AROM'}.get(bond['order'])
            if order is None:raise ValueError('Unsupported ligand bond type: '+bond['order'])
            added['_chem_comp_bond.'].append(dict(comp_id=name,atom_id_1=bond['a'],atom_id_2=bond['b'],value_order=order,pdbx_aromatic_flag='Y' if order=='AROM' else 'N'))
    for prefix,old in saved.items():
        rows=[];identity='id' if prefix=='_chem_comp.' else 'comp_id'
        for i,value in enumerate(old.get(identity,[])):
            if value not in seen:rows.append({k:v[i] for k,v in old.items()})
        rows.extend(added[prefix])
        keys=list(dict.fromkeys(k for row in rows for k in row))
        block.set_mmcif_category(prefix,{k:[r.get(k,False) for r in rows] for k in keys})
    doc.write_file(str(path))


def native_names(smiles,predictor):
    """Pinned Boltz/IntelliFold/ESMFold2 and Protenix SMILES naming rules."""
    from rdkit import Chem
    mol=Chem.AddHs(Chem.MolFromSmiles(smiles))
    if predictor.startswith('protenix') or predictor == 'openfold-3-mlx':
        counts=Counter();names=[]
        for a in mol.GetAtoms():
            e=a.GetSymbol().upper();counts[e]+=1
            if a.GetAtomicNum()!=1:names.append(e+str(counts[e]))
    elif predictor in ('boltz','intellifold','intellifold-full') or predictor.startswith('esmfold2-'):
        ranks=Chem.CanonicalRankAtoms(mol)
        names=[a.GetSymbol().upper()+str(ranks[a.GetIdx()]+1) for a in mol.GetAtoms() if a.GetAtomicNum()!=1]
    else:
        raise ValueError('No audited mixed-target atom mapping for predictor '+predictor)
    return names


def audit_conditioned(atoms, manifest):
    """Native authoring must retain the exact graph and atom identities."""
    reports=[]
    for ligand in manifest['ligands']:
        part=atoms[(atoms.chain_id==ligand['chain']) & (atoms.res_name==ligand['component'])]
        record=molecule_record(part,ligand['source_id'],ligand['chain'],ligand['component'])
        if record['canonical_smiles'] != ligand['canonical_smiles']:
            raise ValueError('Native conditioning changed ligand chemistry: '+ligand['source_id'])
        if {a['name'] for a in record['atoms']} != {a['name'] for a in ligand['atoms']}:
            raise ValueError('Native conditioning changed ligand atom identities.')
        reports.append(dict(source_id=ligand['source_id'],atoms=len(record['atoms']),passed=True))
    return reports


def validate_predictor(config):
    if not config.get('target_ligands'):return
    predictor=config['settings']['predictor']
    for ligand in config['target_ligands']['ligands']:native_names(ligand['smiles'],predictor)


def add_prediction_ligands(document,config):
    for ligand in config.get('target_ligands',{}).get('ligands',[]):
        document['sequences'].append(dict(ligand=dict(id=ligand['chain'],smiles=ligand['smiles'])))
    return document


def protein_interface_scores(scores, chains):
    """Use only explicitly identified protein pairs for protein-design feedback."""
    from itertools import combinations
    directions=scores.get('ipsae_directional',{})
    requested=[f'{a}>{b}' for a in chains for b in chains if a!=b]
    if len(chains)<2 or any(k not in directions or not math.isfinite(float(directions[k])) for k in requested):
        raise ValueError('Mixed-target prediction needs finite directional ipSAE for every protein pair.')
    selected={k:float(directions[k]) for k in requested}
    pairs={f'{a}:{b}':dict(forward=selected[f'{a}>{b}'],reverse=selected[f'{b}>{a}'],
                         minimum=min(selected[f'{a}>{b}'],selected[f'{b}>{a}']),
                         maximum=max(selected[f'{a}>{b}'],selected[f'{b}>{a}'])) for a,b in combinations(chains,2)}
    return {**scores,'ipsae_min':min(p['minimum'] for p in pairs.values()),
            'ipsae_directional':selected,'ipsae_pairs':pairs,
            'ipsae_pair_minimums':{k:v['minimum'] for k,v in pairs.items()},
            'ipsae_directional_n0res':{k:v for k,v in scores.get('ipsae_directional_n0res',{}).items() if k in selected},
            'ipsae_protein_chains':list(chains)}


def context_operation(root,config,source,destination,mode,**options):
    """Use the pinned chemistry runtime, without altering predictor environments."""
    import os,subprocess
    destination=Path(destination);request=destination.with_suffix('.context_request.json')
    result=destination.with_suffix('.context_result.json')
    atomic(request,dict(config=config,source=str(source),destination=str(destination),mode=mode,**options))
    venv=Path(root)/'venvs/NanoHunter_rfd4'
    env=dict(os.environ,VIRTUAL_ENV=str(venv),PATH=str(venv/'bin')+os.pathsep+os.environ.get('PATH',''),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    subprocess.run([str(venv/'bin/python'),'-B',str(Path(__file__).resolve().parents[1]/'rfd4_cli.py'),
                    'mixed-assembly','--root',str(root),'--config',str(request),'--output',str(result)],env=env,check=True)
    report=json.loads(result.read_text())
    if report['source_sha256']!=sha(source):raise ValueError('Assembly source changed during chemistry checks.')
    report['operation_artifacts']=[request,result]
    return report


def execute_context_operation(request,output):
    """CPU-only implementation; model weights and accelerator libraries stay unloaded."""
    source=request['source'];config=request['config'];destination=request['destination']
    if request['mode']=='mpnn-parent':
        normalized=write_mpnn_parent(source,destination,config,request['mapping'])
        report=dict(structure=str(normalized))
    elif request['mode']=='assessment':
        normalized=canonical_assembly(source,destination,config,predictor=request['predictor'])
        report=dict(structure=str(normalized),assembly_audit=assembly_metrics(normalized,config))
    else:raise ValueError('Unknown molecular context operation.')
    atomic(output,dict(source_sha256=sha(source),**report))


def canonical_assembly(source,destination,config,protein_mapping=None,predictor=None):
    """Audit and normalize a complete assembly without dropping any entity."""
    import gemmi
    manifest=config['target_ligands'];structure=gemmi.read_structure(str(source))
    if len(structure)!=1:raise ValueError('Expected one complete molecular assembly.')
    model=structure[0];protein_mapping=protein_mapping or {}
    # Resolve all chains before renaming, so A/B swaps cannot collide.
    for chain in model:
        if chain.name in protein_mapping:chain.name='__protein_'+protein_mapping[chain.name]
    for chain in model:
        if chain.name.startswith('__protein_'):chain.name=chain.name[len('__protein_'):]
    expected=set(config['target_sequences'])|{config['settings']['binder_chain']}|{l['chain'] for l in manifest['ligands']}
    if {c.name for c in model}!=expected or len(model)!=len(expected):
        raise ValueError('The complete assembly changed its protein/ligand chain set.')
    maps=[]
    for ligand in manifest['ligands']:
        chain=model[ligand['chain']]
        if len(chain)!=1:raise ValueError('Ligand instance count changed: '+ligand['source_id'])
        residue=chain[0];residue.remove_hydrogens()
        expected_names=[a['name'] for a in ligand['atoms']]
        observed_names=native_names(ligand['smiles'],predictor) if predictor else expected_names
        atoms={a.name:a for a in residue}
        if len(atoms)!=len(residue) or set(atoms)!=set(observed_names):
            raise ValueError('Ligand atom identity changed: '+ligand['source_id'])
        for native,record in zip(observed_names,ligand['atoms']):
            atom=atoms[native]
            if atom.element.name.upper()!=record['element'] or not all(math.isfinite(v) for v in (atom.pos.x,atom.pos.y,atom.pos.z)):
                raise ValueError('Ligand element or finite-coordinate check failed: '+ligand['source_id'])
            atom.name=record['name'];atom.charge=record['charge']
        residue.name=ligand['component'];residue.seqid=gemmi.SeqId(1,' ')
        maps.append(dict(source_id=ligand['source_id'],chain=ligand['chain'],
                         native_to_source=dict(zip(observed_names,expected_names)),smiles=ligand['smiles']))
    destination=Path(destination).with_suffix('.cif')
    structure.setup_entities();structure.make_mmcif_document().write_file(str(destination))
    write_components(destination,manifest)
    atomic(destination.with_suffix('.atom_map.json'),dict(source_sha256=sha(source),mappings=maps))
    return destination


def write_mpnn_parent(source,destination,config,mapping):
    import gemmi
    normalized=canonical_assembly(source,Path(destination).with_suffix('.cif'),config)
    structure=gemmi.read_structure(str(normalized));model=structure[0]
    mapping=dict(mapping)
    used=set(mapping.values())
    # Imported assemblies may use B for a ligand. MPNN's protein role mapping
    # must not then merge it with the target protein that becomes B.
    for chain in model:
        if chain.name not in mapping:
            available=[c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' if c not in used]
            if not available:raise ValueError('MPNN parent has too many distinct chains for PDB format.')
            name=chain.name if len(chain.name)==1 and chain.name not in used else available[0]
            mapping[chain.name]=name;used.add(name)
    for chain in model:
        if chain.name in mapping:chain.name='__'+mapping[chain.name]
    for chain in model:
        if chain.name.startswith('__'):chain.name=chain.name[2:]
    # RFD4 uses NaN B factors for generated atoms without confidence values.
    # ProDy compares every atom attribute when joining backbone/ligand views;
    # NaN makes even the same AtomGroup compare unequal. B factors are not
    # MPNN inputs. Normalize only this disposable PDB, retaining the raw CIF.
    missing_b=[]
    for chain in model:
        for residue in chain:
            for atom in residue:
                if not math.isfinite(atom.b_iso):
                    missing_b.append(dict(chain=chain.name,residue=str(residue.seqid),atom=atom.name))
                    atom.b_iso=0.0
    structure.write_pdb(str(destination))
    atomic(Path(destination).with_suffix('.chain_map.json'),dict(source_sha256=sha(normalized),source_to_mpnn=mapping,
           nonfinite_b_factors_serialized_as_zero=missing_b,
           b_factor_scope='MPNN input serialization only; coordinates, chemistry and source confidence unchanged.'))
    return normalized


def assembly_metrics(path,config):
    """Separate ligand geometry/context checks from protein-interface confidence."""
    import gemmi
    import numpy as np
    from rdkit import Chem
    model=gemmi.read_structure(str(path))[0];table=Chem.GetPeriodicTable()
    def xyz(chain):return np.array([[a.pos.x,a.pos.y,a.pos.z] for r in chain for a in r if not a.element.is_hydrogen])
    binder=xyz(model[config['settings']['binder_chain']])
    target=np.concatenate([xyz(model[c]) for c in config['target_sequences']])
    reference=config['target_ligands'].get('target_ca',{})
    transform=None
    if reference:
        source=np.concatenate([np.asarray(reference[c],dtype=float) for c in config['target_sequences']])
        predicted=np.array([[a.pos.x,a.pos.y,a.pos.z] for c in config['target_sequences'] for r in model[c] for a in r if a.name=='CA'])
        if source.shape!=predicted.shape or not np.isfinite(source).all():raise ValueError('Target reference coordinates do not match the predicted sequence.')
        pmean=predicted.mean(0);smean=source.mean(0)
        u,_,vt=np.linalg.svd((predicted-pmean).T@(source-smean))
        parity=np.eye(3);parity[-1,-1]=np.linalg.det(u@vt)
        transform=(pmean,smean,u@parity@vt)
    reports=[]
    for ligand in config['target_ligands']['ligands']:
        atoms={a.name:a for a in model[ligand['chain']][0]};coords=xyz(model[ligand['chain']])
        bt=np.linalg.norm(coords[:,None]-binder[None],axis=-1)
        tt=np.linalg.norm(coords[:,None]-target[None],axis=-1)
        other=[xyz(model[l['chain']]) for l in config['target_ligands']['ligands'] if l['chain']!=ligand['chain']]
        other_clashes=int((np.linalg.norm(coords[:,None]-np.concatenate(other)[None],axis=-1)<1).sum()) if other else 0
        bad=[]
        for bond in ligand['bonds']:
            a,b=atoms[bond['a']],atoms[bond['b']]
            length=a.pos.dist(b.pos);radius=table.GetRcovalent(a.element.atomic_number)+table.GetRcovalent(b.element.atomic_number)
            if not .5*radius <= length <= 1.8*radius:bad.append(dict(a=a.name,b=b.name,length_angstrom=length))
        molecule=Chem.MolFromSmiles(ligand['smiles'])
        conformer=Chem.Conformer(molecule.GetNumAtoms())
        for record in ligand['atoms']:
            pos=atoms[record['name']].pos
            conformer.SetAtomPosition(record['index'],(pos.x,pos.y,pos.z))
        molecule.RemoveAllConformers();molecule.AddConformer(conformer)
        expected_stereo={i:tag for i,tag in Chem.FindMolChiralCenters(molecule,includeUnassigned=False)}
        expected_bonds={b.GetIdx():b.GetStereo() for b in molecule.GetBonds() if str(b.GetStereo()) not in ('STEREONONE','STEREOANY')}
        Chem.RemoveStereochemistry(molecule);Chem.AssignStereochemistryFrom3D(molecule)
        actual_stereo=dict(Chem.FindMolChiralCenters(molecule,includeUnassigned=True))
        stereo_ok=(all(actual_stereo.get(i)==tag for i,tag in expected_stereo.items()) and
                   all(molecule.GetBondWithIdx(i).GetStereo()==tag for i,tag in expected_bonds.items()))
        reference_rmsd=None
        if transform:
            pmean,smean,rotation=transform
            ordered=np.array([[atoms[r['name']].pos.x,atoms[r['name']].pos.y,atoms[r['name']].pos.z] for r in ligand['atoms']])
            reference_rmsd=float(np.sqrt(np.mean(np.sum(((ordered-pmean)@rotation+smean-np.array([r['xyz'] for r in ligand['atoms']]))**2,axis=1))))
        reports.append(dict(source_id=ligand['source_id'],chemical_identity_preserved=True, chemical_identity_scope='Input graph and exact mapped atom inventory; coordinate stereochemistry checked separately', target_aligned_ligand_rmsd_angstrom=reference_rmsd, stereochemistry_preserved=stereo_ok,heavy_atoms=len(coords),
                            minimum_binder_distance_angstrom=float(bt.min()),minimum_target_distance_angstrom=float(tt.min()),
                            other_ligand_clashes_below_1A=other_clashes,binder_clashes_below_1A=int((bt<1).sum()),target_clashes_below_1A=int((tt<1).sum()),abnormal_bonds=bad))
    return dict(passed=all(not (not r['stereochemistry_preserved'] or r['abnormal_bonds'] or r['binder_clashes_below_1A'] or r['target_clashes_below_1A'] or r['other_ligand_clashes_below_1A']) for r in reports),
                ligands=reports,criteria='Complete identities; finite coordinates; bond lengths 0.5–1.8 times summed covalent radii; no protein–ligand heavy-atom separations below 1 Å.',
                scope='Assembly integrity/geometry, not binding affinity or independent validation')


def inspect_existing(root, cfg, destination):
    """Audit imported or annotated assemblies before a search can drop context."""
    import os
    from .prepare import runtime
    os.environ.update(DEBUG='false',PROJECT_ROOT=str(runtime(root)/'sources/RFD4-Proteina'))
    from atomworks.io.parser import parse
    from rfproteina.utils.parse_presets import RCSB_WITH_METALS
    from .search_engine import sequences
    destination=Path(destination)
    paths=cfg['starting_structures'] or [str(destination/'annotated.cif')]
    expected=None;manifest=None;outputs=[]
    source_chemistry=None
    if cfg['starting_structures'] and cfg['source']:
        source_atoms=parse(cfg['source'],config=RCSB_WITH_METALS.replace(build_assembly=None,altloc='first'))['asym_unit'][0]
        source_mask=ligand_mask(source_atoms);source_chemistry=[]
        keys=list(dict.fromkeys((str(c),int(r),str(i),str(n)) for c,r,i,n in zip(source_atoms.chain_id[source_mask],source_atoms.res_id[source_mask],source_atoms.ins_code[source_mask],source_atoms.res_name[source_mask])))
        for c,r,i,n in keys:
            part=source_atoms[source_mask & (source_atoms.chain_id==c) & (source_atoms.res_id==r) & (source_atoms.ins_code==i) & (source_atoms.res_name==n)]
            source_chemistry.append(molecule_record(part,f'{c}:{r}{i}:{n}',c,n)['canonical_smiles'])
    for index,path in enumerate(paths):
        # Annotated RFD4 inputs contain unknown generated-protein placeholders.
        # Do not apply experimental-structure atom completion/valence repair to
        # those placeholders. Every actual ligand is sanitized below by RDKit.
        preset=RCSB_WITH_METALS.replace(build_assembly=None,altloc='first')
        if not cfg['starting_structures']:preset=preset.replace(add_missing_atoms=False)
        atoms=parse(path,config=preset)['asym_unit'][0]
        if not cfg['starting_structures']:
            placeholders=(atoms.chain_id==cfg['binder_chain']) & ((atoms.res_name=='<M>') | (atoms.element=='X'))
            atoms=atoms[~placeholders]
        mask=ligand_mask(atoms)
        rows=[]
        keys=list(dict.fromkeys((str(c),int(r),str(i),str(n)) for c,r,i,n in zip(atoms.chain_id[mask],atoms.res_id[mask],atoms.ins_code[mask],atoms.res_name[mask])))
        for c,r,i,n in keys:
            selected=mask & (atoms.chain_id==c) & (atoms.res_id==r) & (atoms.ins_code==i) & (atoms.res_name==n)
            if atoms.bonds is not None and any(bool(selected[a])!=bool(selected[b]) for a,b,_ in atoms.bonds.as_array()):
                raise ValueError('Covalently linked context requires a bonded-assembly workflow.')
            part=atoms[selected]
            if c==cfg['binder_chain'] or (any((atoms.chain_id==c)&~mask)) or len(set(atoms.res_id[atoms.chain_id==c]))!=1:
                raise ValueError('Imported molecular context needs each ligand on its own chain, separate from protein chains.')
            row=molecule_record(part,f'{c}:{r}{i.strip()}:{n}',c,n)
            row['residue']=r;rows.append(row)
        signature=[(r['chain'],r['canonical_smiles'],[(a['name'],a['element']) for a in r['atoms']]) for r in rows]
        if source_chemistry is not None and Counter(source_chemistry)!=Counter(r['canonical_smiles'] for r in rows):raise ValueError('Imported starting assemblies do not retain all ligand chemistry from the requested source.')
        if expected is not None and expected!=signature:raise ValueError('Imported families differ in retained ligand chemistry or atom identities.')
        expected=signature
        if not rows:continue
        target_ca={str(c):atoms.coord[(atoms.chain_id==c)&(atoms.atom_name=='CA')&~mask].tolist() for c in dict.fromkeys(atoms.chain_id[~mask]) if c!=cfg['binder_chain']}
        current=dict(schema=1,source_sha256=sha(path),ligands=rows,target_ca=target_ca,omitted_by_explicit_selection=[])
        if manifest is None:manifest=current
        if cfg['starting_structures']:
            observed=sequences(path);targets={c:s for c,s in observed.items() if c!=cfg['binder_chain']}
            config=dict(settings=cfg,target_sequences=targets,target_ligands=manifest)
            validate_predictor(config)
            out=canonical_assembly(path,destination/f'imported_{index:05d}.cif',config)
            outputs.append(str(out))
    if manifest:
        atomic(destination/'target_ligands.json',manifest)
        if outputs:atomic(destination/'starting_assemblies.json',outputs)
    atomic(destination/'context_audit.json',dict(passed=True,inputs=[dict(path=p,sha256=sha(p)) for p in paths],ligands=len(expected or [])))
