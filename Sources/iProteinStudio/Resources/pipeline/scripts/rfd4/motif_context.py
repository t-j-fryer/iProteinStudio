"""Retain explicitly selected binding partners in the motif's source frame."""
import copy
from pathlib import Path
from .contract import atomic, sha


def inventory(atoms):
    import biotite.structure as bs
    from biotite.sequence import ProteinSequence
    protein = bs.filter_amino_acids(atoms)
    chains = []
    for c in dict.fromkeys(map(str, atoms.chain_id[protein])):
        _, names = bs.get_residues(atoms[protein & (atoms.chain_id == c)])
        chains.append(dict(chain=c, sequence=''.join(ProteinSequence.convert_letter_3to1(n) for n in names)))
    # Nucleic acids are not offered as binding partners in this workflow.
    other = ~(protein | bs.filter_solvent(atoms) | bs.filter_nucleotides(atoms))
    keys = list(dict.fromkeys((str(c), int(r), str(i), str(n)) for c,r,i,n in
                zip(atoms.chain_id[other], atoms.res_id[other], atoms.ins_code[other], atoms.res_name[other])))
    ligands = [dict(id=f'{c}:{r}{i.strip()}:{n}', chain=c, residue=r, insertion_code=i, name=n) for c,r,i,n in keys]
    return dict(chains=chains, ligands=ligands)


def prepare(atoms, cfg, destination):
    import numpy as np
    import biotite.structure as bs
    from .mixed_target import molecule_record
    m = copy.deepcopy(cfg['motif']); info = inventory(atoms)
    partners = m.get('partner_chains') or []; selected = m.get('ligand_ids') or []
    chain_info = {r['chain']: r for r in info['chains']}; ligand_info = {r['id']: r for r in info['ligands']}
    if set(partners) - set(chain_info) or set(selected) - set(ligand_info):
        raise ValueError('A retained partner is absent from the inspected source complex.')
    source_chain = m['residues'][0]['chain']; protein = bs.filter_amino_acids(atoms)
    parts = [atoms[protein & (atoms.chain_id == source_chain)].copy()]
    parts[0].chain_id[:] = 'A'
    for row in m['residues']: row['chain'] = 'A'
    identities = []; anchor = []; ligands = []; target_ca = {}
    for i,c in enumerate(partners):
        part = atoms[protein & (atoms.chain_id == c)].copy(); out = chr(66+i)
        residues = list(bs.residue_iter(part))
        for pos,res in enumerate(residues,1):
            ca = res[res.atom_name == 'CA']
            if len(ca) != 1 or not np.isfinite(ca.coord).all(): raise ValueError('Partner residues need one finite C-alpha each.')
            anchor.append(dict(chain=out, position=pos, atom='CA', xyz=ca.coord[0].tolist()))
        target_ca[out] = part.coord[part.atom_name == 'CA'].tolist()
        part.chain_id[:] = out; parts.append(part)
        identities.append(dict(source_chain=c, native_chain=out, output_chain=out, sequence=chain_info[c]['sequence']))
    for i,label in enumerate(selected):
        row = ligand_info[label]
        mask = (atoms.chain_id == row['chain']) & (atoms.res_id == row['residue']) & (atoms.ins_code == row['insertion_code']) & (atoms.res_name == row['name'])
        if atoms.bonds is not None and any(bool(mask[a]) != bool(mask[b]) for a,b,_ in atoms.bonds.as_array()):
            raise ValueError('Covalently linked partners require a bonded-assembly workflow.')
        part = atoms[mask].copy(); out = chr(66+len(partners)+i); component = 'L;'+'0123456789ABCDEFGHIJKLMNOP'[i]
        ligand = molecule_record(part,label,out,component); ligands.append(ligand)
        part = part[~np.isin(part.element,['H','D'])]; part.chain_id[:] = out; part.res_id[:] = 1; part.ins_code[:] = ''; part.res_name[:] = component
        parts.append(part)
        anchor.extend(dict(chain=out,position=1,atom=a['name'],xyz=a['xyz']) for a in ligand['atoms'])
    combined = parts[0]
    for part in parts[1:]: combined = combined + part
    destination = Path(destination)
    atomic(destination/'target_identity.json',dict(chains=identities))
    metadata = dict(schema=1,source_sha256=sha(cfg['source']),source_motif_chain=source_chain,binder_chain='A',anchors=anchor,partner_chains=[r['output_chain'] for r in identities])
    if (cfg.get('motif_assessment') or {}).get('placement_rmsd_max') is not None:
        from motif_beta.geometry import fit
        coords=np.array([a['xyz'] for a in anchor])
        fit(coords,coords)
    atomic(destination/'motif_context.json',metadata)
    if ligands:
        manifest = dict(schema=1,source_sha256=sha(cfg['source']),ligands=ligands,target_ca=target_ca,protein_chains=metadata['partner_chains'],omitted_by_explicit_selection=[k for k in ligand_info if k not in selected])
        if cfg.get('motif_assessment') and cfg['motif_assessment']['holo']:
            from .mixed_target import validate_predictor
            validate_predictor(dict(settings=cfg,target_ligands=manifest))
        atomic(destination/'target_ligands.json',manifest)
    else: manifest = None
    return combined, dict(cfg,motif=m), manifest


def extend_spec(spec, cfg, atoms):
    """Use a shared coordinate group so motif and partner geometry stays related."""
    from .targets import residue_segments
    chains = list(dict.fromkeys(map(str, atoms.chain_id)))
    for c in chains:
        if c == 'A': continue
        spec['contig'] += ',/0,' + residue_segments(c,atoms.res_id[atoms.chain_id == c])
        condition = 'C_CRD' if cfg['motif']['coordinate_mode'] == 'absolute' else 'C_CRDGRP'
        value = True if condition == 'C_CRD' else 1
        spec['conditions'].setdefault(condition,{}).setdefault(value,[]).append(dict(select=f"sel('{c}') and not has_nan_coord()"))
        spec['conditions'].setdefault('C_SEQ',{}).setdefault(True,[]).append(dict(select=f"sel('{c}')"))
    return spec


def freeze_reference(path, cfg, destination):
    """Record the native authored component IDs; never infer unindexed placement."""
    from .motif_metrics import cif_atoms, xyz
    rows = cif_atoms(path)
    selected = [a for a in rows if a['label_asym_id']=='A' and int(a.get('condition_CoordinateGroup_1_atom','-1'))>=0]
    wanted = sum(len(r['atoms']) for r in cfg['motif']['residues'])
    if len(selected) != wanted: raise ValueError('Native authoring changed the requested motif atom inventory.')
    native_residues=list(dict.fromkeys(a['label_seq_id'] for a in selected))
    original=sorted(cfg['motif']['residues'],key=lambda r:r['residue'])
    if len(native_residues)!=len(original):raise ValueError('Native authoring changed motif residue count.')
    correspondence=dict(zip(native_residues,original))
    import json
    source_chain=json.loads((Path(destination)/'motif_context.json').read_text())['source_motif_chain']
    atoms=[]
    for a in selected:
        source=correspondence[a['label_seq_id']]
        if a['label_atom_id'] not in source['atoms']:raise ValueError('Native authoring changed motif atom correspondence.')
        atoms.append(dict(origin=a['label_asym_id']+a['label_seq_id'],source_residue=f"{source_chain}:{source['residue']}",atom=a['label_atom_id'],component=a['label_comp_id'],xyz=xyz(a)))
    if cfg.get('motif_assessment'):
        import numpy as np
        from motif_beta.geometry import fit
        coords=np.array([a['xyz'] for a in atoms]);fit(coords,coords)
    atomic(Path(destination)/'motif_reference.json',dict(schema=1,atoms=atoms,source_sha256=sha(cfg['source']),atom_policy='Exact selected names; no symmetry reassignment'))
