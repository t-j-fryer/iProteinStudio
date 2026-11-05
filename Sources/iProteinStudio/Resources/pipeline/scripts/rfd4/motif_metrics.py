"""Source-anchored, named-atom motif scoring with native insertion provenance."""
import json
from pathlib import Path
import numpy as np
from motif_beta.geometry import fit, rmsd


def cif_atoms(path):
    import gemmi
    table=gemmi.cif.read_file(str(path)).sole_block().find_mmcif_category('_atom_site.')
    tags=[k.removeprefix('_atom_site.') for k in table.tags]
    return [dict(zip(tags,list(row))) for row in table]


def xyz(a): return [float(a['Cartn_'+d]) for d in 'xyz']


def structure_atoms(path):
    """Position means sequence position, not an assumed PDB residue number."""
    import gemmi
    structure=gemmi.read_structure(str(path))
    if len(structure)!=1: raise ValueError('Expected one predicted structural model.')
    result={}
    for chain in structure[0]:
        for position,residue in enumerate(chain,1):
            for atom in residue:
                if atom.element.is_hydrogen: continue
                key=(chain.name,position,atom.name)
                coords=[atom.pos.x,atom.pos.y,atom.pos.z]
                if atom.has_altloc() or key in result or not np.isfinite(coords).all():
                    raise ValueError('Ambiguous or nonfinite assessment atom: '+str(key))
                result[key]=dict(xyz=coords,component=residue.name)
    return result


def insertion_map(native, reference):
    wanted={(a['origin'],a['atom']):a for a in reference['atoms']}
    selected={};positions={};residues={}
    for a in cif_atoms(native):
        chain=a['label_asym_id'];residue=a['label_seq_id']
        residues.setdefault(chain,[])
        if residue not in residues[chain]: residues[chain].append(residue)
        origin=a.get('annotation_src-coordinate-conditioned-region_1_atom','.')
        key=(origin,a['label_atom_id'])
        if key not in wanted: continue
        if key in selected: raise ValueError('Native motif atom mapping is ambiguous.')
        selected[key]=a
    if set(selected)!=set(wanted): raise ValueError('Native motif provenance is incomplete; cannot call a hit.')
    mapped=[]
    for key,ref in wanted.items():
        a=selected[key]
        mapped.append(dict(**ref,chain=a['label_asym_id'],position=residues[a['label_asym_id']].index(a['label_seq_id'])+1))
    if {a['chain'] for a in mapped}!={'A'}: raise ValueError('Native motif is not on the designed chain A.')
    return mapped


def score(path, mapped, context, *, fix_sequence, holo):
    observed=structure_atoms(path);mobile=[];reference=[]
    for a in mapped:
        key=(a['chain'],a['position'],a['atom'])
        if key not in observed: raise ValueError('Prediction is missing a required motif atom: '+str(key))
        row=observed[key]
        if fix_sequence and row['component']!=a['component']: raise ValueError('Prediction changed a fixed motif identity.')
        mobile.append(row['xyz']);reference.append(a['xyz'])
    mobile=np.array(mobile);reference=np.array(reference)
    rotation,translation=fit(mobile,reference)
    result=dict(motif_rmsd_angstrom=rmsd(mobile@rotation+translation,reference),motif_atoms=len(mapped),atom_policy='Exact selected names; one proper rigid fit; no symmetry permutation')
    if holo:
        anchors=context['anchors'];target=[];source=[]
        for a in anchors:
            key=(a['chain'],a['position'],a['atom'])
            if key not in observed: raise ValueError('Prediction lost a retained partner anchor: '+str(key))
            target.append(observed[key]['xyz']);source.append(a['xyz'])
        try:
            r,t=fit(np.array(target),np.array(source))
            result['partner_aligned_motif_rmsd_angstrom']=rmsd(mobile@r+t,reference)
        except ValueError as exc:
            result['partner_aligned_motif_rmsd_angstrom']=None
            result['placement_unavailable']=str(exc)
    return result


def hit_verdict(assessments, policy):
    required=[k for k in ('apo','holo') if policy[k]]
    if set(assessments)!=set(required): raise ValueError('Incomplete requested apo/holo assessment.')
    gates=[]
    for mode in required:
        if policy['rmsd_max'] is not None:
            value=assessments[mode].get('motif_rmsd_angstrom')
            gates.append(isinstance(value,(float,int)) and np.isfinite(value) and value<=policy['rmsd_max'])
    if policy['placement_rmsd_max'] is not None:
        value=assessments['holo'].get('partner_aligned_motif_rmsd_angstrom')
        gates.append(isinstance(value,(float,int)) and np.isfinite(value) and value<=policy['placement_rmsd_max'])
    # No threshold means unclassified, never an automatic hit.
    return all(gates) if gates else None
