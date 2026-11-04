"""Typed motif selections compiled to the pinned upstream condition-spec dialect."""
import json
import re
from pathlib import Path


def validate(cfg):
    motif = cfg.get('motif')
    if motif is None:
        return
    keys = {'residues', 'coordinate_mode', 'fix_sequence', 'unindexed', 'group_segments', 'prefix', 'linker', 'suffix'}
    if not isinstance(motif, dict) or set(motif) - {'source_sha256'} != keys:
        raise ValueError('Supply the complete typed motif configuration.')
    if motif.get('source_sha256') is not None and (not isinstance(motif['source_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', motif['source_sha256'])):
        raise ValueError('Invalid inspected motif source fingerprint.')
    if cfg['task'] != 'motif' or cfg['annotated_input'] or cfg['contig'] or cfg['starting_structures']:
        raise ValueError('Typed motifs use an ordinary source structure, without an annotated input or manual contig.')
    if cfg['hotspots'] or cfg.get('hotspot_residues'):
        raise ValueError('Use extra native conditions for motif hotspots, not protein-binder hotspot controls.')
    if any(row.get('condition') in ('C_CRD', 'C_CRDGRP', 'C_SEQ', 'C_IDX') for row in cfg['conditions'] if isinstance(row, dict)):
        raise ValueError('Set motif geometry, sequence and indexing in the motif controls; do not override them in extra conditions.')
    if motif['coordinate_mode'] not in ('absolute', 'relative'):
        raise ValueError('Choose absolute coordinates or one relative coordinate group.')
    for key in ('fix_sequence', 'unindexed', 'group_segments'):
        if type(motif[key]) is not bool:
            raise ValueError(key + ' must be true or false.')
    for key in ('prefix', 'linker', 'suffix'):
        value = motif[key]
        if not isinstance(value, list) or len(value) != 2 or any(type(n) is not int for n in value) or not 0 <= value[0] <= value[1] <= 2000:
            raise ValueError('Motif segment lengths require ordered integer bounds from 0 to 2000.')
        if value[0] == 0 and value[1] != 0:
            raise ValueError('Use 0–0 to omit a segment, or a positive minimum length.')
    rows = motif['residues']
    if not isinstance(rows, list) or not rows:
        raise ValueError('Select at least one motif residue and its coordinate atoms.')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'chain', 'residue', 'atoms'}:
            raise ValueError('Each motif residue needs a chain, residue number and atom names.')
        if not isinstance(row['chain'], str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', row['chain']) or type(row['residue']) is not int or row['residue'] < 1:
            raise ValueError('Use native chain IDs and positive input residue numbers.')
        key = (row['chain'], row['residue'])
        if key in seen:
            raise ValueError('Duplicate motif residue.')
        seen.add(key)
        atoms = row['atoms']
        if not isinstance(atoms, list) or not atoms or any(not isinstance(a, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', a) for a in atoms) or len(set(atoms)) != len(atoms):
            raise ValueError('Select unique, explicit coordinate atom names.')
        if not motif['fix_sequence'] and set(atoms) - {'N', 'CA', 'C', 'O'}:
            raise ValueError('Sidechain coordinates reveal residue identity; keep sequence fixed or select backbone atoms only.')
    # The guided form creates a single protein scaffold. Native annotated CIFs
    # remain the explicit route for multi-chain or non-protein motifs.
    if len({r['chain'] for r in rows}) != 1:
        raise ValueError('The guided motif scaffold uses one source protein chain; use native annotated input for multi-chain motifs.')
    minimum, maximum = scaffold_length_bounds(motif)
    if motif['unindexed'] and minimum < len(rows):
        raise ValueError('Free-placement motifs need at least one generated scaffold position per selected residue.')
    if maximum > 2000:
        raise ValueError('The maximum scaffold length exceeds 2000 residues.')


def scaffold_length_bounds(motif):
    # Upstream unindexing removes source residues; insertion assigns them to
    # generated positions instead of adding more residues to the scaffold.
    return [sum(motif[k][i] for k in ('prefix', 'suffix')) + motif['linker'][i] * (len(segments(motif['residues'])) - 1) + (0 if motif['unindexed'] else len(motif['residues'])) for i in (0, 1)]


def segments(rows):
    groups = []
    for row in sorted(rows, key=lambda r: (r['chain'], r['residue'])):
        if not groups or row['chain'] != groups[-1][-1]['chain'] or row['residue'] != groups[-1][-1]['residue'] + 1:
            groups.append([])
        groups[-1].append(row)
    return groups


def compile_spec(motif, atoms):
    """Reject absent/nonfinite atoms, then delegate all semantics to upstream."""
    import numpy as np
    import biotite.structure as bs
    protein = bs.filter_amino_acids(atoms)
    conditions, tokens = {}, []
    def add(name, value, selection, group=None):
        row = dict(select=selection)
        if group is not None:
            row['group'] = group
        conditions.setdefault(name, {}).setdefault(value, []).append(row)
    def insert(bounds):
        if bounds[1]:
            tokens.append(f'{bounds[0]}-{bounds[1]}')
    insert(motif['prefix'])
    for group_number, rows in enumerate(segments(motif['residues']), 1):
        if group_number > 1:
            insert(motif['linker'])
        chain = rows[0]['chain']
        tokens.append(f"{chain}{rows[0]['residue']}-{rows[-1]['residue']}")
        for row in rows:
            mask = (atoms.chain_id == chain) & (atoms.res_id == row['residue'])
            if not mask.any() or not protein[mask].all():
                raise ValueError('Motif selection is not a source protein residue: ' + str(row))
            for atom in row['atoms']:
                selected = mask & (atoms.atom_name == atom)
                if int(selected.sum()) != 1 or not np.isfinite(atoms.coord[selected]).all():
                    raise ValueError(f'Motif atom {chain}{row["residue"]}:{atom} is absent, ambiguous or lacks coordinates.')
            residue = f"sel('{chain}/*/{row['residue']}')"
            selection = f"sel('{chain}/*/{row['residue']}/[{','.join(row['atoms'])}]')"
            add('C_CRD' if motif['coordinate_mode'] == 'absolute' else 'C_CRDGRP', True if motif['coordinate_mode'] == 'absolute' else 1, selection)
            add('C_SEQ', motif['fix_sequence'], residue)
            if motif['unindexed']:
                group = f'segment_{group_number}' if motif['group_segments'] else f"residue_{row['residue']}"
                add('C_IDX', False, residue, group)
    insert(motif['suffix'])
    return ','.join(tokens), conditions


def inspect(source, destination, root):
    """Use the same native parser as authoring; preview uses these exact IDs."""
    import os
    from .prepare import runtime
    os.environ.update(DEBUG='false', PROJECT_ROOT=str(runtime(root) / 'sources/RFD4-Proteina'))
    import numpy as np
    import gemmi
    import biotite.structure as bs
    from atomworks.io.parser import parse
    from rfproteina.utils.parse_presets import RCSB_WITH_METALS
    from .contract import atomic, sha
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    # Bind the preview to one byte-for-byte input, even if an external editor
    # changes the selected file while parsing is in progress.
    original = Path(source)
    source = destination / ('source' + original.suffix)
    source.write_bytes(original.read_bytes())
    atoms = parse(str(source), config=RCSB_WITH_METALS.replace(build_assembly=None, altloc='first'))['asym_unit'][0]
    atoms = atoms[bs.filter_amino_acids(atoms)]
    rows = []
    structure = gemmi.Structure(); model = gemmi.Model('1')
    for chain in dict.fromkeys(map(str, atoms.chain_id)):
        gc = gemmi.Chain(chain)
        for number in dict.fromkeys(map(int, atoms.res_id[atoms.chain_id == chain])):
            selected = atoms[(atoms.chain_id == chain) & (atoms.res_id == number)]
            finite = selected[np.isfinite(selected.coord).all(axis=1) & (selected.element != 'H')]
            if not len(finite):
                continue
            names = list(map(str, finite.atom_name))
            if len(set(names)) != len(names):
                raise ValueError('Ambiguous native residue atom identity.')
            rows.append(dict(chain=chain, residue=number, name=str(finite.res_name[0]), atoms=names))
            gr = gemmi.Residue(); gr.name = str(finite.res_name[0]); gr.seqid = gemmi.SeqId(number, ' ')
            for a in finite:
                ga = gemmi.Atom(); ga.name = str(a.atom_name); ga.element = gemmi.Element(str(a.element)); ga.pos = gemmi.Position(*map(float, a.coord)); gr.add_atom(ga)
            gc.add_residue(gr)
        model.add_chain(gc)
    if not rows:
        raise ValueError('No protein residues with finite coordinates were found.')
    structure.add_model(model)
    preview = destination/'motif-preview.cif'; structure.make_mmcif_document().write_file(str(preview))
    result = dict(source_sha256=sha(source), preview=str(preview), residues=rows)
    atomic(destination/'motif-inspection.json', result)
    print(json.dumps(result))
