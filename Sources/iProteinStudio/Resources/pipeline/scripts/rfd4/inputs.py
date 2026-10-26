"""Input conveniences using Studio conformers and qualified native VHH authoring.

No model inference: the native writer and feature audit still own conditioning.
"""
import json
import os
from pathlib import Path
import sys
from .contract import atomic, sha


def ligand_source(root, smiles, destination):
    import gemmi
    import numpy as np
    from rdkit import Chem
    sys.path.insert(0, str(Path(root) / 'rfd3_scripts'))
    from ligand_intelligence import generate_ensemble, conformer_budget
    from rdkit.Chem import rdMolDescriptors
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1:
        raise ValueError('Enter one connected molecule as a valid SMILES string.')
    canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
    mol, energies, field = generate_ensemble(mol, conformer_budget(rdMolDescriptors.CalcNumRotatableBonds(mol)))
    valid = [row for row in energies if row[2]]
    if not valid: raise ValueError('No conformer converged; provide an explicit molecular structure.')
    conformer = min(valid, key=lambda row: (row[1], row[0]))[0]
    check = Chem.Mol(mol)
    Chem.RemoveStereochemistry(check); Chem.AssignStereochemistryFrom3D(check, confId=conformer)
    if Chem.MolToSmiles(check, isomericSmiles=True) != canonical:
        raise ValueError('The conformer stereochemistry differs from the SMILES. Specify every stereocentre or supply a structure.')
    xyz = np.array(mol.GetConformer(conformer).GetPositions()); xyz -= xyz.mean(0)
    names = [atom.GetSymbol() + str(i + 1) for i, atom in enumerate(mol.GetAtoms())]
    doc = gemmi.cif.Document(); block = doc.add_new_block('studio_ligand')
    loop = block.init_loop('_atom_site.', ['group_PDB','id','type_symbol','label_atom_id','label_alt_id','label_comp_id','label_asym_id','label_entity_id','label_seq_id','pdbx_PDB_ins_code','auth_seq_id','auth_comp_id','auth_asym_id','auth_atom_id','B_iso_or_equiv','occupancy','pdbx_formal_charge','Cartn_x','Cartn_y','Cartn_z','pdbx_PDB_model_num'])
    for i, atom in enumerate(mol.GetAtoms()):
        loop.add_row(['HETATM',str(i+1),atom.GetSymbol(),names[i],'.','L;G','B','1','1','.','1','L;G','B',names[i],'0','1',str(atom.GetFormalCharge()),*[f'{v:.6f}' for v in xyz[i]],'1'])
    block.init_loop('_entity.', ['id','type']).add_row(['1','non-polymer'])
    block.init_loop('_chem_comp.', ['id','name','type']).add_row(['L;G','studio_ligand','NON-POLYMER'])
    atoms = block.init_loop('_chem_comp_atom.', ['comp_id','atom_id','type_symbol','charge','pdbx_aromatic_flag','pdbx_leaving_atom_flag','pdbx_model_Cartn_x_ideal','pdbx_model_Cartn_y_ideal','pdbx_model_Cartn_z_ideal'])
    for i, atom in enumerate(mol.GetAtoms()):
        atoms.add_row(['L;G',names[i],atom.GetSymbol(),str(atom.GetFormalCharge()),'Y' if atom.GetIsAromatic() else 'N','N',*[f'{v:.6f}' for v in xyz[i]]])
    bonds = block.init_loop('_chem_comp_bond.', ['comp_id','atom_id_1','atom_id_2','value_order','pdbx_aromatic_flag'])
    for bond in mol.GetBonds():
        order = 'AROM' if bond.GetIsAromatic() else {1.0:'SING',2.0:'DOUB',3.0:'TRIP'}[bond.GetBondTypeAsDouble()]
        bonds.add_row(['L;G',names[bond.GetBeginAtomIdx()],names[bond.GetEndAtomIdx()],order,'Y' if bond.GetIsAromatic() else 'N'])
    path = Path(destination) / 'molecule.cif'; doc.write_file(str(path))
    atomic(Path(destination) / 'molecule.json', dict(canonical_smiles=canonical, source_sha256=sha(path),
        conformer=conformer, force_field=field, seed=20260811, atom_names=names, stereochemistry_verified=True))
    return path


def nanobody_source(root, cfg, destination):
    import biotite.structure as bs
    from biotite.sequence import ProteinSequence
    from atomworks.io.parser import parse
    from atomworks.io.utils.io_utils import to_cif_file
    from rfproteina.utils.parse_presets import RCSB_WITH_METALS
    from .prepare import write_condition_spec_cif
    from nanobody_cdrs import parse_explicit, resolve_cdrs
    preset = RCSB_WITH_METALS.replace(build_assembly=None, altloc='first')
    scaffold = Path(root) / 'examples/nanobody_scaffolds/structures' / (cfg['scaffold_id'] + '.pdb')
    provenance = json.loads((scaffold.parent / 'PROVENANCE.json').read_text())[cfg['scaffold_id']]
    if sha(scaffold) != provenance['sha256']: raise ValueError('The installed framework structure changed.')
    a = parse(scaffold, config=preset)['asym_unit'][0]
    a = a[bs.filter_amino_acids(a)]; a.chain_id[:] = 'A'
    numbers, _ = bs.get_residues(a)
    if list(numbers) != list(range(1, len(numbers)+1)):
        raise ValueError('The framework must use contiguous one-based residue numbers.')
    b = parse(cfg['source'], config=preset)['asym_unit'][0]
    from .targets import selected_chains, residue_segments, hotspot_map
    b = b[bs.filter_amino_acids(b)]
    chains = selected_chains(b.chain_id, cfg['source_target_chain'])
    hot = hotspot_map(cfg, chains)
    targets = []; identities = []; target_segments = []; selections = []
    for i, chain in enumerate(chains):
        part = b[b.chain_id == chain].copy()
        output_chain = chr(66+i)
        residues = list(dict.fromkeys(int(n) for n in part.res_id))
        if not set(hot[chain]) <= set(residues): raise ValueError('A requested target hotspot is absent.')
        part.chain_id[:] = output_chain
        target_segments.append(residue_segments(output_chain, residues))
        _, names = bs.get_residues(part)
        identities.append(dict(source_chain=chain, native_chain=output_chain, output_chain=output_chain,
            sequence=''.join(ProteinSequence.convert_letter_3to1(x) for x in names)))
        targets.append(part)
        if hot[chain]: selections.append(f"sel('{output_chain}/*/{hot[chain]}') and not sel('*/*/*/[N,CA,C,O]') and not has_nan_coord()")
    _, names = bs.get_residues(a); sequence = ''.join(ProteinSequence.convert_letter_3to1(x) for x in names)
    ranges = resolve_cdrs(sequence, explicit=parse_explicit(cfg['cdr_ranges']))['ranges']
    mutable = {i for first,last in ranges.values() for i in range(first,last+1)}
    pieces=[]; i=1
    while i <= len(sequence):
        moving=i in mutable; j=i
        while j < len(sequence) and ((j+1 in mutable) == moving): j+=1
        pieces.append(f'{j-i+1}-{j-i+1}' if moving else f'A{i}-{j}'); i=j+1
    fixed = sorted(set(range(1,len(sequence)+1))-mutable); fs=f"sel('A/*/{fixed}')"
    target_selection = ' or '.join(f"sel('{row['output_chain']}')" for row in identities)
    conditions = {'C_CRD':{True:[dict(select=f"({target_selection}) and sel('*/*/*/[N,CA,C,O]') and not has_nan_coord()")]},
        'C_CRDGRP':{1:[dict(select=fs+" and sel('*/*/*/[N,CA,C,O]') and not has_nan_coord()")]},
        'C_SEQ':{True:[dict(select=f"({target_selection}) or "+fs)]},'C_CATH':{'2.60.40.x':[dict(select="sel('A')")]}}
    if selections: conditions['C_HOT']={True:[dict(select=selection) for selection in selections]}
    reference=Path(destination)/'reference.cif'
    combined = a
    for part in targets: combined = combined + part
    to_cif_file(combined,reference)
    spec=dict(input=str(reference),contig=','.join(pieces)+',/0,'+',/0,'.join(target_segments),conditions=conditions)
    if cfg['conditions'] or cfg['contig']: raise ValueError('Use annotated input for custom framework conditions.')
    write_condition_spec_cif('studio_nanobody',spec,Path(destination)/'annotated.cif',spec_dir=Path(destination),validate=True)
    atomic(Path(destination)/'condition_spec.json',spec)
    atomic(Path(destination)/'target_identity.json',dict(chains=identities))
    atomic(Path(destination)/'framework_identity.json',dict(sequence=sequence,ranges=ranges,source_sha256=sha(scaffold)))


def ligand_pdb(source, destination):
    import biotite.structure as bs
    import biotite.structure.io.pdbx as pdbx
    import biotite.structure.io.pdb as pdb
    atoms=pdbx.get_structure(pdbx.CIFFile.read(source),model=1)
    protein=bs.filter_amino_acids(atoms)
    if len(set(atoms.chain_id[protein])) != 1: raise ValueError('Expected one ligand-binding protein chain.')
    atoms.chain_id[protein]='A'; atoms.chain_id[~protein]='B'
    atoms.res_name[~protein]='LIG'
    output=pdb.PDBFile();output.set_structure(atoms);output.write(destination)
    return destination
