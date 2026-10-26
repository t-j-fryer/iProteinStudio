"""Sparse residue guides from released motifs or explicitly selected proteins.

This is an input exporter, not a scaffold generator. Query length, sequence and
residue placement must already be specified. It never fabricates backbone atoms
or treats an imported protein as the immutable benchmark scoring reference.
"""
import json
from pathlib import Path
from .contract import atomic, case, digest, DATA
from .geometry import LETTERS, read, source_key, fit, rmsd
import numpy as np


def prepare(identifier, mapping, sequence, output, *, structure=None):
    c = case(identifier)
    expected = {r['source_selector'] for r in c['protein_motif']}
    if not isinstance(mapping, dict) or set(mapping) != expected:
        raise ValueError('Supply an exact source-selector to query-position map for every motif residue.')
    if not sequence or set(sequence) - set(LETTERS.values()):
        raise ValueError('Supply a complete protein query sequence using the 20 standard amino acids.')
    positions = list(mapping.values())
    if (any(type(p) is not int or not 1 <= p <= len(sequence) for p in positions)
            or len(set(positions)) != len(positions)):
        raise ValueError('Query positions must be distinct 1-based integers within the sequence.')
    source = Path(structure) if structure is not None else DATA / c['source_file']
    keys = {source_key(r) for r in c['protein_motif']}
    residues = read(source, selected_keys=keys)
    atoms, identities, selected_atoms, source_xyz, observed_xyz = {}, {}, [], [], []
    for r in c['protein_motif']:
        key = source_key(r)
        if key not in residues or residues[key]['component'] != r['component']:
            raise ValueError('Source protein lacks the exact motif residue identity: ' + key)
        residue = residues[key]
        required = {'N', 'CA', 'C', 'O'} | set(r['conditioning_atoms'])
        if not required <= set(residue['atoms']):
            raise ValueError('Source motif needs observed N/CA/C/O and all selected catalytic atoms: ' + key)
        # Reject degenerate local frames rather than constructing missing geometry.
        frame = np.array([residue['atoms'][a]['xyz'] for a in ('N', 'CA', 'C')])
        fit(frame, frame)
        pos = mapping[r['source_selector']]
        if sequence[pos - 1] != LETTERS[r['component']]:
            raise ValueError('Query identity differs from the source motif at position ' + str(pos))
        mapped = f'A:{pos}:'
        atoms[mapped], identities[mapped] = residue, r['component']
        for a in r['conditioning_atoms']:
            if residue['atoms'][a]['element'] != r['atoms'][a]['element'].upper():
                raise ValueError('Source motif atom element differs: ' + key + '/' + a)
            selected_atoms.append([mapped, a])
            source_xyz.append(r['atoms'][a]['xyz_angstrom'])
            observed_xyz.append(residue['atoms'][a]['xyz'])
    observed_xyz, source_xyz = np.array(observed_xyz), np.array(source_xyz)
    selected_rmsd, alignment_note = None, 'A unique rigid fit needs at least three noncollinear selected atoms.'
    if (len(observed_xyz) >= 3 and
            min(np.linalg.matrix_rank(observed_xyz - observed_xyz.mean(0), tol=1e-6),
                np.linalg.matrix_rank(source_xyz - source_xyz.mean(0), tol=1e-6)) >= 2):
        rotation, translation = fit(observed_xyz, source_xyz)
        selected_rmsd = rmsd(observed_xyz @ rotation + translation, source_xyz)
        alignment_note = 'One global selected-atom fit; diagnostic only.'
    # Keep the entire imported motif in ONE source frame. The comparison is
    # diagnostic only; never fit each residue separately or replace benchmark data.
    result = dict(schema=1, kind='sparse-residue-guide', query_length=len(sequence),
        case_id=identifier, source_pdb_id=c['pdb_id'], source_sha256=digest(source),
        benchmark_sha256=c['source_sha256'], source_to_query=mapping,
        source_mode='imported-protein-residues' if structure is not None else 'benchmark-residues',
        atoms=atoms, identities=identities, selected_atoms=selected_atoms,
        selected_atom_rmsd_to_benchmark=selected_rmsd, selected_atom_alignment=alignment_note,
        ligand_policy='Protein template only; ligands are separate predictor inputs. No ligand pose lock.',
        scoring_reference=False, backbone_generated=False)
    output = Path(output)
    if output.exists() and json.loads(output.read_text()) != result:
        raise ValueError('Cannot change a saved source guide; choose a new output.')
    atomic(output, result)
    return result
