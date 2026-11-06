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


def atom_settings(policy, smiles, manifest):
    """Translate only a verified chemical-graph correspondence, never atom order."""
    from rdkit import Chem
    cfg = normalize(policy)
    original, used = Chem.MolFromSmiles(smiles), Chem.MolFromSmiles(manifest['smiles_used'])
    if original is None or used is None or Chem.MolToSmiles(original) != Chem.MolToSmiles(used):
        raise ValueError('Geometry atom selections require the exact predicted chemical state. Use the predictor\'s displayed SMILES and select again.')
    selected = set(cfg['contact_atoms'] + cfg['exposed_atoms'])
    if any(i >= original.GetNumAtoms() for i in selected):
        raise ValueError('Geometry atom index is outside the supplied molecule.')
    matches = used.GetSubstructMatches(original, uniquify=False, useChirality=True, maxMatches=10000)
    if not matches or any(len(m) != original.GetNumAtoms() for m in matches):
        raise ValueError('No complete ligand chemical-graph correspondence.')
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
                exposure_mode=cfg['mode'])
