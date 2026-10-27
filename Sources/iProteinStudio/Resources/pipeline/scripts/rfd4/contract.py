"""Portable RFD4 requests and immutable receipts; no model imports.

Generation follows the released Diffusers model configuration. Search selection
is transferred from the completed fixed/iterative/beam validation campaigns.
"""
import hashlib
import json
import math
from pathlib import Path

REVISIONS = dict(upstream='2db07bb444d91695f8c10e6acb7648e9297f9221',
                 diffusers='3421fed4a1655508436a5ca0c5179e88b0ec0afd',
                 prep='c9959efdebd75ac7fe9129fbbf0e291a6e0487d5',
                 model='92fc3ae50e336b2ec59c713c19cfd43e5d3e923b')
TASKS = ('monomer', 'protein', 'ligand', 'nanobody', 'motif', 'partial', 'inverse', 'annotated')
SEARCHES = ('native', 'fixed', 'iterative', 'greedy', 'beam')
# These are the pinned native condition names, not an RFD3 translation.
CONDITIONS = ('C_CRD', 'C_SEQ', 'C_IDX', 'C_CRDGRP', 'C_CENTROID', 'C_HOT', 'C_RAS',
              'C_SEC', 'C_HB', 'C_PISTACK', 'C_PICATION', 'C_SALT', 'C_HPHOB', 'C_MCOORD', 'C_CATH')
RESIDUE_LETTERS = dict(zip('ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN PRO GLN ARG SER THR VAL TRP TYR'.split(),
                          'ACDEFGHIKLMNPQRSTVWY'))


def residue_letter(name):
    if name not in RESIDUE_LETTERS: raise ValueError('Nonstandard protein residue: ' + str(name))
    return RESIDUE_LETTERS[name]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''): h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temp.replace(path)


def fixed(path, value):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError('Saved RFD4 settings changed: ' + str(path))
    else: atomic(path, value)


def seal(path, result, files, relative_root=None):
    path = Path(path).resolve()
    record = dict(result=result, files={str(Path(f).resolve()): sha(f) for f in files})
    if relative_root is not None: record['relative_root'] = str(Path(relative_root).resolve())
    atomic(path, record)


def verify(path, seen=None, relative_root=None):
    path = Path(path).resolve()
    seen = set() if seen is None else seen
    if path in seen: return
    seen.add(path)
    record = json.loads(path.read_text())
    relative_root = record.get('relative_root', relative_root)
    if relative_root is not None:
        relative_root = Path(relative_root).resolve()
        if relative_root not in path.parents: raise ValueError('Receipt is outside its declared campaign root.')
    # NISE Journal schema 1 stores paths relative to the campaign, whereas
    # ESMFold2's completion format stores them relative to the prediction leaf.
    nise = record.get('schema') == 1 and 'prediction' in record.get('result', {})
    if nise and relative_root is None: raise ValueError('NISE receipt verification requires its explicit campaign root.')
    if not record.get('files'): raise ValueError('Empty completion receipt: ' + str(path))
    for name, digest in record['files'].items():
        artifact = Path(name)
        if not artifact.is_absolute():
            base = relative_root if nise else path.parent
            artifact = (base / artifact).resolve()
            if base not in artifact.parents: raise ValueError('Receipt artifact escaped its declared root.')
        if not artifact.is_file() or sha(artifact) != digest:
            raise ValueError('Saved RFD4 artifact changed: ' + str(artifact))
        if artifact.name in ('complete.json', 'completed.json') or artifact.name.endswith('_completed.json'):
            verify(artifact, seen, relative_root)
    return record.get('result')


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}.')
    return value


def normalize(request):
    if not isinstance(request, dict): raise ValueError('RFD4 requires a settings object.')
    defaults = dict(schema=1, task='monomer', source='', length=120, count=1, seed=42,
                    target_chain='B', binder_chain='A', source_target_chain='', hotspots=[], contig='', conditions=[],
                    partial_fraction=0.5, search='native', cycles=5, proposals=4, beam_width=4,
                    sequence_model='solublempnn', predictor='esmfold2-full-mlx',
                    target_msa='', scaffold_msa='', cdr_ranges='', omit_amino_acids='C',
                    temperature=0.1, optimized_kernels=False, annotated_input=False,
                    assess_native=False, starting_structures=[], native_search=False,
                    native_beam_width=2, native_branches=2, native_checkpoints=[8, 15],
                    native_partial_fraction=0.5, ligand_smiles='', time_budget_minutes=None, scaffold_id=None,
                    hotspot_residues=None)
    unknown = set(request) - set(defaults)
    if unknown: raise ValueError('Unknown RFD4 settings: ' + ', '.join(sorted(unknown)))
    cfg = {**defaults, **request}
    if cfg['time_budget_minutes'] is not None and (type(cfg['time_budget_minutes']) not in (int, float)
            or not math.isfinite(cfg['time_budget_minutes']) or not 0 < cfg['time_budget_minutes'] <= 10080):
        raise ValueError('Design time must be positive and no more than seven days.')
    if cfg['scaffold_id'] is not None and (cfg['task'] != 'nanobody' or cfg['scaffold_id'] != '7xl0_vobarilizumab'):
        raise ValueError('Choose an installed, qualified nanobody framework.')
    if cfg['scaffold_msa'] == 'auto' and not cfg['scaffold_id']:
        raise ValueError('Automatic scaffold alignment requires a selected framework; choose an explicit alignment for a custom framework.')
    if cfg['scaffold_id'] and (cfg['binder_chain'] != 'A' or cfg['target_chain'] != 'B'):
        raise ValueError('Automatic framework assembly uses binder A and target B. Use a custom annotated input for other chain roles.')
    if cfg['schema'] != 1 or cfg['task'] not in TASKS or cfg['search'] not in SEARCHES:
        raise ValueError('Choose a supported RFD4 task and search policy.')
    for key, low, high in [('length', 1, 2000), ('count', 1, 10000), ('seed', 0, 2**32-1),
                           ('cycles', 1, 100), ('proposals', 1, 64), ('beam_width', 1, 64)]:
        integer(cfg[key], key, low, high)
    if cfg['seed'] + cfg['count'] - 1 >= 2**32:
        raise ValueError('The requested generation seeds exceed the 32-bit range.')
    for key in ('optimized_kernels', 'annotated_input', 'assess_native', 'native_search'):
        if type(cfg[key]) is not bool: raise ValueError(key + ' must be true or false.')
    for key in ('source', 'target_chain', 'binder_chain', 'source_target_chain', 'contig', 'target_msa', 'scaffold_msa', 'cdr_ranges', 'omit_amino_acids', 'ligand_smiles'):
        if not isinstance(cfg[key], str): raise ValueError(key + ' must be text.')
    if not isinstance(cfg['starting_structures'], list) or any(not isinstance(v, str) or not v for v in cfg['starting_structures']):
        raise ValueError('Starting structures must be an explicit list of files.')
    if cfg['starting_structures'] and len(cfg['starting_structures']) != cfg['count']:
        raise ValueError('The number of starting structures must match the requested families.')
    if cfg['task'] == 'protein' and cfg['contig']:
        raise ValueError('Omit contig for protein de novo design; Studio derives it from the target chain.')
    if cfg['starting_structures'] and cfg['search'] == 'native' and not cfg['assess_native'] and not cfg['native_search']:
        raise ValueError('Choose a search or assessment when importing starting structures.')
    if cfg['task'] != 'monomer' and not cfg['source'] and not cfg['starting_structures'] and not (cfg['task'] == 'ligand' and cfg['ligand_smiles']):
        raise ValueError('Choose the source structure or annotated RFD4 CIF.')
    if cfg['task'] in ('nanobody', 'motif') and not cfg['annotated_input'] and not cfg['contig'] and not cfg['starting_structures'] and not cfg['scaffold_id']:
        raise ValueError('Define the retained residues and generated segments, or supply an annotated RFD4 CIF.')
    if not cfg['binder_chain'] or not cfg['target_chain'] or cfg['binder_chain'] == cfg['target_chain']:
        raise ValueError('Choose distinct binder and target chains.')
    if not isinstance(cfg['hotspots'], list) or any(type(v) is not int or v < 1 for v in cfg['hotspots']):
        raise ValueError('Hotspots must be positive source residue numbers.')
    if len(set(cfg['hotspots'])) != len(cfg['hotspots']): raise ValueError('Duplicate hotspot residue.')
    if cfg['hotspot_residues'] is not None:
        if not isinstance(cfg['hotspot_residues'], list) or any(not isinstance(v, str) for v in cfg['hotspot_residues']):
            raise ValueError('Chain-qualified hotspots must be a list of residue identifiers.')
    if (type(cfg['partial_fraction']) not in (int, float) or not math.isfinite(cfg['partial_fraction'])
            or not 0 < cfg['partial_fraction'] <= 1):
        raise ValueError('Partial diffusion fraction must be greater than zero and at most one.')
    if type(cfg['temperature']) not in (int, float) or not math.isfinite(cfg['temperature']) or not 0 < cfg['temperature'] <= 2:
        raise ValueError('Sequence temperature must be greater than zero and at most two.')
    if set(cfg['omit_amino_acids']) - set('ACDEFGHIKLMNPQRSTVWY'):
        raise ValueError('Excluded amino acids must use standard one-letter codes.')
    if not isinstance(cfg['conditions'], list): raise ValueError('Conditions must be a list.')
    for row in cfg['conditions']:
        if not isinstance(row, dict) or set(row) - {'condition', 'value', 'selection', 'group'}:
            raise ValueError('Invalid RFD4 condition row.')
        if row.get('condition') not in CONDITIONS or not isinstance(row.get('selection'), str) or not row['selection'].strip():
            raise ValueError('Choose a native condition and an explicit atom selection.')
        if type(row.get('value')) not in (str, int, float, bool): raise ValueError('Condition value is missing.')
    if cfg['native_search']:
        if cfg['task'] not in ('protein', 'nanobody', 'ligand') or cfg['search'] != 'native':
            raise ValueError('Native rollout search requires a protein/nanobody/ligand task and generated sequences.')
        if cfg['assess_native']: raise ValueError('Native search already assesses every rollout.')
        for key in ('native_beam_width', 'native_branches'): integer(cfg[key], key, 1, 16)
        fraction = cfg['native_partial_fraction']
        if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 < fraction < 1:
            raise ValueError('Native search requires a partial trajectory fraction between zero and one.')
        steps = cfg['native_checkpoints']
        if not isinstance(steps, list) or not steps or any(type(n) is not int or not 1 <= n <= round(60*fraction) for n in steps) or steps != sorted(set(steps)):
            raise ValueError('Native checkpoints must be unique, increasing step numbers within the partial trajectory.')
        if cfg['task'] == 'ligand' and (not isinstance(cfg['ligand_smiles'], str) or not cfg['ligand_smiles']):
            raise ValueError('Native ligand search requires the exact source molecule SMILES for Boltz scoring.')
    if cfg['task'] == 'ligand' and (cfg['search'] != 'native' or cfg['assess_native'] or cfg['native_search']):
        if cfg['predictor'] != 'boltz' or not cfg['ligand_smiles']:
            raise ValueError('Small-molecule search requires Boltz and the exact molecule SMILES.')
        if cfg['search'] != 'native' and cfg['sequence_model'] != 'lasermpnn':
            raise ValueError('Small-molecule sequence search requires LASErMPNN.')
        if cfg['search'] != 'native' and cfg['omit_amino_acids'] != 'C':
            raise ValueError('The qualified ligand sampler excludes cysteine; custom exclusions are not supported.')
        if cfg['search'] == 'beam' and cfg['beam_width'] > cfg['proposals']:
            raise ValueError('The first generation must supply every beam place.')
    elif cfg['search'] != 'native' or cfg['assess_native'] or cfg['native_search']:
        if cfg['task'] not in ('protein', 'nanobody'):
            raise ValueError('Protein search requires a protein target or nanobody input. Ligand searches use NISE.')
        expected = ('abmpnn',) if cfg['task'] == 'nanobody' else ('solublempnn', 'proteinmpnn')
        if cfg['sequence_model'] not in expected: raise ValueError('Choose a sequence designer appropriate for this task.')
        if cfg['predictor'] not in ('esmfold2-full-mlx', 'esmfold2-fast-mlx', 'esmfold2-600-mlx', 'boltz'):
            raise ValueError('Choose Full, Fast, 600M or Boltz for protein search.')
        if cfg['predictor'] not in {'esmfold2-fast-mlx', 'esmfold2-600-mlx'} and not cfg['target_msa']:
            raise ValueError('Select the target alignment, or explicitly enter empty for single-sequence prediction.')
        if cfg['task'] == 'nanobody' and (not cfg['cdr_ranges'] or (cfg['predictor'] not in {'esmfold2-fast-mlx', 'esmfold2-600-mlx'} and not cfg['scaffold_msa'])):
            raise ValueError('Nanobody search requires explicit CDR ranges and a scaffold alignment (or empty).')
        if cfg['search'] == 'beam' and cfg['beam_width'] > cfg['proposals']:
            raise ValueError('The first generation must supply at least one candidate for every beam place.')
    return cfg


def prediction_budget(cfg):
    if cfg['native_search']:
        terminal = int(cfg['native_checkpoints'][-1] < round(60 * cfg['native_partial_fraction']))
        return cfg['count'] * cfg['native_beam_width'] * (cfg['native_branches'] * len(cfg['native_checkpoints']) + terminal)
    if cfg['search'] == 'native': return cfg['count'] if cfg['assess_native'] else 0
    if cfg['search'] == 'fixed': return cfg['count'] * cfg['proposals']
    if cfg['search'] == 'iterative': return cfg['count'] * cfg['cycles']
    parents = cfg['beam_width'] if cfg['search'] == 'beam' else 1
    return cfg['count'] * cfg['proposals'] * (1 + parents * (cfg['cycles'] - 1))


def select(rows, width):
    if len(rows) < width or any(not math.isfinite(r['score']) for r in rows):
        raise ValueError('Incomplete or nonfinite search generation; refusing to select parents.')
    # Same stable family-wide ranking as the completed beam experiment; no elitism.
    return sorted(rows, key=lambda r: (-r['score'], r['id']))[:width]
