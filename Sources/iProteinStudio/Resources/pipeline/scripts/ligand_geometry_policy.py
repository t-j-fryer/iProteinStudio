"""Portable optional ligand hit policy. Atom indices refer to the supplied SMILES.

The Figure 4 classifier itself lives in nise/ and is deliberately unchanged.
"""
import math

DEFAULTS = dict(schema=1, mode='sasa', contact_atoms=[], exposed_atoms=[],
                contact_distance=6.0, exposure_min_fraction=0.5)


def normalize(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('Unknown ligand geometry hit-filter settings.')
    cfg = {**DEFAULTS, **value}
    if type(cfg['schema']) is not int or cfg['schema'] != 1 or cfg['mode'] not in ('sasa', 'biotin-carboxamide-v1'):
        raise ValueError('Choose selected-atom accessibility or the Figure 4 free-biotin exit policy.')
    for key in ('contact_atoms', 'exposed_atoms'):
        values = cfg[key]
        if not isinstance(values, list) or any(type(v) is not int or v < 0 for v in values) or len(set(values)) != len(values):
            raise ValueError(key + ' must contain distinct zero-based input SMILES atom indices.')
    for key, low, high in (('contact_distance', 0.1, 20), ('exposure_min_fraction', 0.01, 1)):
        v = cfg[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('Invalid ligand geometry ' + key + '.')
    if set(cfg['contact_atoms']) & set(cfg['exposed_atoms']):
        raise ValueError('An atom cannot require both binding contact and linker exposure.')
    if not cfg['contact_atoms'] and not cfg['exposed_atoms'] and cfg['mode'] == 'sasa':
        raise ValueError('Select at least one contact or exposed atom for the geometry hit filter.')
    return cfg


def _chemical_smiles(molecule):
    """Atom-map annotations do not define a chemical state or atom order."""
    from rdkit import Chem
    molecule = Chem.Mol(molecule)
    for atom in molecule.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(molecule)


def _boltz_correspondence(original, smiles, used, manifest):
    """Trace native standardization with labels; never infer a relaxed match."""
    import hashlib
    from pathlib import Path
    from rdkit import Chem

    message = ('Geometry atom selections cannot be mapped safely to the predicted chemical state. '
               'Use the scoring engine\'s chemical state and select its atoms again.')
    # A different chemical state is allowed only when the pinned Boltz parser
    # actually produced it. Other predictors retain the exact-state contract.
    if manifest.get('standardized') is not True or not manifest.get('boltz_parser_sha256'):
        raise ValueError(message)
    import boltz.data.parse.schema as schema
    parser_sha = hashlib.sha256(Path(schema.__file__).read_bytes()).hexdigest()
    if manifest['boltz_parser_sha256'] != parser_sha:
        raise ValueError(message)
    supplied = Chem.MolFromSmiles(manifest.get('input_smiles', ''))
    native_smiles = schema.standardize(smiles)
    native = Chem.MolFromSmiles(native_smiles) if native_smiles else None
    if supplied is None or native is None or _chemical_smiles(supplied) != _chemical_smiles(original) or _chemical_smiles(native) != _chemical_smiles(used):
        raise ValueError(message)

    tagged = Chem.Mol(original)
    for atom in tagged.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    traced_smiles = schema.standardize(Chem.MolToSmiles(tagged, canonical=False))
    traced = Chem.MolFromSmiles(traced_smiles) if traced_smiles else None
    count = original.GetNumAtoms()
    if traced is None or traced.GetNumAtoms() != count:
        raise ValueError(message)
    labels = [atom.GetAtomMapNum() for atom in traced.GetAtoms()]
    if set(labels) != set(range(1, count + 1)) or len(set(labels)) != count:
        raise ValueError(message)
    order = [labels.index(i + 1) for i in range(count)]
    # Permit only the native parser's state/representation changes. Labels must
    # prove that every atom, isotope, edge and specified stereocentre survives.
    for first, index in zip(original.GetAtoms(), order):
        second = traced.GetAtomWithIdx(index)
        if (first.GetAtomicNum(), first.GetIsotope()) != (second.GetAtomicNum(), second.GetIsotope()):
            raise ValueError(message)
        if first.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED and not first.HasProp('_CIPCode'):
            raise ValueError(message)
        if first.HasProp('_CIPCode') and (not second.HasProp('_CIPCode') or first.GetProp('_CIPCode') != second.GetProp('_CIPCode')):
            raise ValueError(message)
    edges = {tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))) for b in original.GetBonds()}
    traced_edges = {tuple(sorted((labels[b.GetBeginAtomIdx()] - 1, labels[b.GetEndAtomIdx()] - 1))) for b in traced.GetBonds()}
    if edges != traced_edges:
        raise ValueError(message)
    for bond in original.GetBonds():
        if bond.GetStereo() not in (Chem.BondStereo.STEREONONE, Chem.BondStereo.STEREOANY):
            other = traced.GetBondBetweenAtoms(order[bond.GetBeginAtomIdx()], order[bond.GetEndAtomIdx()])
            if other.GetStereo() != bond.GetStereo():
                raise ValueError(message)
    for atom in traced.GetAtoms():
        atom.SetAtomMapNum(0)
    if _chemical_smiles(traced) != _chemical_smiles(used):
        raise ValueError(message)
    return traced, order, parser_sha


def atom_settings(policy, smiles, manifest):
    """Translate only a verified chemical-graph correspondence, never atom order."""
    from rdkit import Chem
    cfg = normalize(policy)
    original, used = Chem.MolFromSmiles(smiles), Chem.MolFromSmiles(manifest['smiles_used'])
    if original is None or used is None:
        raise ValueError('Geometry atom selections require a valid input and predicted chemical state.')
    changed = _chemical_smiles(original) != _chemical_smiles(used)
    query, order, parser_sha = original, list(range(original.GetNumAtoms())), None
    if changed:
        query, order, parser_sha = _boltz_correspondence(original, smiles, used, manifest)
    selected = set(cfg['contact_atoms'] + cfg['exposed_atoms'])
    if any(i >= original.GetNumAtoms() for i in selected):
        raise ValueError('Geometry atom index is outside the supplied molecule.')
    matches = used.GetSubstructMatches(query, uniquify=False, useChirality=True, maxMatches=10000)
    matches = [tuple(match[i] for i in order) for match in matches]
    if not matches or any(len(m) != original.GetNumAtoms() for m in matches):
        raise ValueError('No complete ligand chemical-graph correspondence.')
    if len(matches) == 10000:
        raise ValueError('Too many equivalent ligand atom mappings to verify geometry selections safely.')
    # Equivalent atoms are safe only when every correspondence preserves each
    # requested set. A single selected oxygen of a symmetric group is ambiguous.
    for key in ('contact_atoms', 'exposed_atoms'):
        if len({tuple(sorted(m[i] for i in cfg[key])) for m in matches}) != 1:
            raise ValueError('Geometry selection is ambiguous under ligand symmetry; select the complete equivalent atom group.')
    names = {a['index']: a['name'] for a in manifest['atoms']}
    if set(names) != set(range(used.GetNumAtoms())) or len(set(names.values())) != len(names):
        raise ValueError('Incomplete or duplicate predictor ligand atom map.')
    return dict(hotspot_atoms=[names[matches[0][i]] for i in cfg['contact_atoms']],
                exposed_atoms=[names[matches[0][i]] for i in cfg['exposed_atoms']],
                hotspot_distance=cfg['contact_distance'], exposure_min_fraction=cfg['exposure_min_fraction'],
                exposure_mode=cfg['mode'],
                atom_correspondence=dict(method='boltz-native-standardization-v1' if changed else 'exact-chemical-graph-v1',
                                         chemical_state_changed=changed, input_to_manifest=list(matches[0]),
                                         equivalent_matches=len(matches), boltz_parser_sha256=parser_sha))
