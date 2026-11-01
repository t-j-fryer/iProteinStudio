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
                    hotspot_residues=None, length_plan=None, hit_filters=None)
    unknown = set(request) - set(defaults)
    if unknown: raise ValueError('Unknown RFD4 settings: ' + ', '.join(sorted(unknown)))
    cfg = {**defaults, **request}
    if cfg['time_budget_minutes'] is not None and (type(cfg['time_budget_minutes']) not in (int, float)
            or not math.isfinite(cfg['time_budget_minutes']) or not 0 < cfg['time_budget_minutes'] <= 10080):
        raise ValueError('Design time must be positive and no more than seven days.')
    if cfg['scaffold_id'] is not None and (cfg['task'] != 'nanobody' or cfg['scaffold_id'] not in SCAFFOLDS):
        raise ValueError('Choose a bundled nanobody framework or a custom annotated input.')
    if cfg['scaffold_id'] and not cfg['cdr_ranges']:
        import csv
        catalog=Path(__file__).resolve().parents[2]/'examples/nanobody_scaffolds/catalog.tsv'
        entries={r['scaffold_id']:r for r in csv.DictReader(catalog.read_text().splitlines(),delimiter='\t')}
        row=entries[cfg['scaffold_id']]
        cfg['cdr_ranges']=','.join(f"CDR{i}:"+row[f'cdr{i}_range_1based'] for i in (1,2,3))
    if cfg['scaffold_msa'] == 'auto' and not cfg['scaffold_id']:
        raise ValueError('Automatic scaffold alignment requires a selected framework; choose an explicit alignment for a custom framework.')
    if cfg['scaffold_id'] and (cfg['binder_chain'] != 'A' or cfg['target_chain'] != 'B'):
        raise ValueError('Automatic framework assembly uses binder A and target B. Use a custom annotated input for other chain roles.')
    if cfg['schema'] != 1 or cfg['task'] not in TASKS or cfg['search'] not in SEARCHES:
        raise ValueError('Choose a supported RFD4 task and search policy.')
    for key, low, high in [('length', 1, 2000), ('count', 1, 10000), ('seed', 0, 2**32-1),
                           ('cycles', 1, 100), ('proposals', 1, 64), ('beam_width', 1, 64)]:
        integer(cfg[key], key, low, high)
    allocated_lengths(cfg)
    validate_hit_filters(cfg)
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
        if cfg['predictor'] not in PREDICTORS:
            raise ValueError('Choose a supported structure predictor.')
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


SCAFFOLDS = ('7xl0_vobarilizumab', '7eow_caplacizumab', '8coh_gefurulimab',
             '8z8v_ozoralizumab_alb8', 'gontivimab', 'isecarosmab', 'sonelokimab', '3eak_nbbcii10_fgla')
PREDICTORS = ('esmfold2-full-mlx', 'esmfold2-fast-mlx', 'esmfold2-600-mlx', 'boltz',
              'intellifold', 'intellifold-full', 'protenix-v2', 'protenix-mini',
              'protenix-constraint-v0.5', 'openfold-3-mlx')


def predictor_identity(name):
    if name not in PREDICTORS: raise ValueError('Unknown RFD4 predictor: ' + str(name))
    engine = 'intellifold' if name == 'intellifold-full' else name
    if name.startswith('esmfold2-'): runtime, model = 'esmfold2', name
    elif name.startswith('intellifold'): runtime, model = 'intellifold', ('v2' if name.endswith('-full') else 'v2-flash')
    elif name.startswith('protenix-'): runtime, model = ('protenix_constraint' if 'constraint' in name else 'protenix'), name
    elif name == 'openfold-3-mlx': runtime, model = 'openfold3_mlx', 'openfold3'
    else: runtime, model = 'boltz', 'boltz2'
    return dict(engine=engine, runtime=runtime, model=model)


def allocated_lengths(cfg):
    plan = cfg.get('length_plan')
    if plan is None: return [cfg['length']] * cfg['count']
    if cfg['task'] not in ('monomer', 'protein', 'ligand') or cfg['starting_structures'] or cfg['annotated_input'] or cfg['native_search']:
        raise ValueError('Length allocation requires newly generated monomers or binders without native diffusion search.')
    if not isinstance(plan, dict) or set(plan) - {'minimum','maximum','counts'}:
        raise ValueError('Invalid length allocation.')
    low=integer(plan.get('minimum'), 'minimum length', 1, 2000)
    high=integer(plan.get('maximum'), 'maximum length', low, 2000)
    count=integer(cfg['count'], 'count', 1, 10000)
    counts=plan.get('counts')
    if counts is not None:
        if not isinstance(counts, dict) or not counts: raise ValueError('Custom length counts are empty.')
        remaining={}
        for key, n in counts.items():
            if not isinstance(key,str) or not key.isdigit() or str(int(key))!=key: raise ValueError('Use integer lengths.')
            remaining[integer(int(key),'length',low,high)]=integer(n,'length count',1,10000)
        if sum(remaining.values()) != count: raise ValueError('Length counts must add up to the family count.')
        result=[]
        while len(result)<count:
            for key in sorted(remaining):
                if remaining[key]: result.append(key);remaining[key]-=1
        return result
    if count < high-low+1:
        if count==1:return [(low+high)//2]
        return [low+int(i*(high-low)/(count-1)+0.5) for i in range(count)]
    return [low+i%(high-low+1) for i in range(count)]


def family_config(config, index):
    cfg=config['settings']
    if not cfg.get('length_plan'): return config
    length=allocated_lengths(cfg)[index]
    path=config.get('length_inputs',{}).get(str(length))
    if not path:raise ValueError('Missing audited input for family length ' + str(length))
    return dict(config, annotated_cif=path, settings=dict(cfg,length=length))


def validate_hit_filters(cfg):
    filters=cfg.get('hit_filters')
    if filters is None:return
    if not isinstance(filters,dict):raise ValueError('Hit filters must be metric cutoffs.')
    for key, value in filters.items():
        if key not in ('ipsae_min','iptm','complex_plddt') or type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
            raise ValueError('Protein hit cutoffs must be between 0 and 1.')
    if filters and (cfg['task'] not in ('protein','nanobody') or not (cfg['search']!='native' or cfg['assess_native'] or cfg['native_search'])):
        raise ValueError('Protein hit filters require protein or nanobody assessment.')


def filter_verdict(cfg, scores):
    filters=cfg.get('hit_filters')
    if not filters:return {}
    failed=[]
    for name, cutoff in filters.items():
        value=scores.get(name)
        if value is None or not math.isfinite(float(value)) or float(value)<cutoff: failed.append(name)
    return dict(hit_filter_passed=not failed, hit_filter_failures=failed,
                hit_filter_cutoffs=filters, hit_filter_scope='design_feedback_not_independent_validation')
