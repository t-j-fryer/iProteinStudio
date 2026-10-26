"""Portable, immutable AME inputs and bounded beta requests (stdlib only)."""
import hashlib
import json
import math
from pathlib import Path
import re

DATA = Path(__file__).resolve().parent / 'data'
PROFILE = 'studio-ame-beta-v2'
POLICIES = ('fixed', 'iterative', 'greedy', 'beam')
DESIGNERS = ('ligandmpnn', 'lasermpnn')
ENGINES = ('boltz', 'protenix-v2', 'intellifold')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.part')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    tmp.replace(path)


def catalog():
    return json.loads((DATA / 'inventory.json').read_text())


def case(identifier):
    rows = [c for c in catalog()['cases'] if c['case_id'] == identifier]
    if len(rows) != 1:
        raise ValueError('Choose a released AME-41 case.')
    c = rows[0]
    source = DATA / c['source_file']
    if digest(source) != c['source_sha256']:
        raise ValueError('Benchmark coordinate checksum changed: ' + identifier)
    for residue in c['protein_motif'] + c['ligands']:
        if residue['insertion_code']:
            raise ValueError('Insertion codes require an explicit mapping adapter.')
        for a in residue['atoms'].values():
            if len(a['xyz_angstrom']) != 3 or not all(math.isfinite(x) for x in a['xyz_angstrom']):
                raise ValueError('Nonfinite reference coordinates.')
    return c


def normalize(raw):
    defaults = dict(schema=1, profile=PROFILE, case_id='M0040_13pk', length=180, roots=1,
                    cycles=2, proposals=4, beam_width=4, seed=0,
                    policies=list(POLICIES), designers=list(DESIGNERS),
                    engine='boltz', guidance=True, guidance_source='rfd3-root', ligand_profile='fixedligand',
                    source_tolerance=1.0, stage='prepare')
    unknown = set(raw) - set(defaults)
    if unknown:
        raise ValueError('Unknown motif beta settings: ' + ', '.join(sorted(unknown)))
    cfg = {**defaults, **raw}
    if cfg['profile'] != PROFILE:
        raise ValueError('This beta scoring profile changed; prepare a new run with original-input motif ranking.')
    if cfg['schema'] != 1 or cfg['ligand_profile'] != 'fixedligand':
        raise ValueError('This beta runs the fixed-ligand profile only; partial-ligand masks remain in the source inventory.')
    for key, lo, hi in [('length', 50, 400), ('roots', 1, 5), ('cycles', 1, 10),
                        ('proposals', 1, 32), ('beam_width', 1, 8), ('seed', 0, 2147483647)]:
        if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
            raise ValueError(f'{key} must be an integer between {lo} and {hi}.')
    for key, choices in [('policies', POLICIES), ('designers', DESIGNERS)]:
        values = cfg[key]
        if (not isinstance(values, list) or not values or len(set(values)) != len(values)
                or any(v not in choices for v in values)):
            raise ValueError('Select distinct supported ' + key + '.')
    if cfg['engine'] not in ENGINES or type(cfg['guidance']) is not bool:
        raise ValueError('Select a supported guide engine and an explicit guidance state.')
    if cfg['guidance_source'] not in ('rfd3-root', 'benchmark-residues'):
        raise ValueError('Select generated RFD3 or original benchmark residue frames.')
    if (type(cfg['source_tolerance']) not in (int, float)
            or not math.isfinite(cfg['source_tolerance']) or not 0 < cfg['source_tolerance'] <= 2.5):
        raise ValueError('Source functional-atom guard must be >0 and <=2.5 Angstrom.')
    if cfg['stage'] not in ('prepare', 'backbones', 'cycles'):
        raise ValueError('Choose preparation, backbone pilot or beta cycles.')
    if cfg['stage'] == 'cycles' and cfg['engine'] != 'boltz':
        raise ValueError('Beta cycling currently supports Boltz-2. Protenix and IntelliFold mapped templates can be exported for qualification.')
    c = case(cfg['case_id'])
    if cfg['stage'] != 'prepare' and sum(len(r['conditioning_atoms']) for r in c['protein_motif']) < 3:
        raise ValueError('This motif has fewer than three selected atoms. Source templates can be prepared, but the beta source-alignment scoring guard needs a qualified ligand-anchored definition before inference.')
    if cfg['length'] < len(c['protein_motif']):
        raise ValueError('The scaffold cannot be shorter than its motif.')
    return cfg


def budget(cfg):
    candidates = cfg['roots'] * cfg['cycles'] * cfg['proposals']
    return dict(proposals_per_arm=candidates,
                arms=len(cfg['policies']) * len(cfg['designers']),
                proposal_predictions_per_arm=candidates if cfg['guidance'] else 0,
                untemplated_search_checks_per_arm=candidates,
                final_assessment='separate, untemplated predictor family; not included',
                accounting='Same total proposals per cycle for every policy, not per beam member.')


def prepare(output, raw):
    """Materialize exact inputs; never execute the upstream Hydra strings."""
    output = Path(output).resolve()
    cfg = normalize(raw)
    receipt = output / 'bundle.json'
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved['request'] != cfg:
            raise ValueError('This beta bundle has different settings. Create a new run.')
        verify(output)
        return saved
    c = case(cfg['case_id'])
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'source.pdb'
    source.write_bytes((DATA / c['source_file']).read_bytes())
    # ORI is metadata, not chemistry. Retain exact coordinate bytes separately.
    selected = {(r['chain'], r['residue'], r['component']) for r in c['protein_motif'] + c['ligands']}
    lines = [line for line in source.read_text().splitlines()
             if line.startswith(('ATOM  ', 'HETATM'))
             and (line[21], int(line[22:26]), line[17:20].strip()) in selected]
    # AtomWorks splits mixed polymer/non-polymer chains during native parsing.
    # Assign every ligand instance an explicit unused chain before selection,
    # retaining a reversible map to the byte-identical benchmark source.
    used = {r['chain'] for r in c['protein_motif'] + c['ligands']}
    available = [ch for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' if ch not in used]
    if len(available) < len(c['ligands']):
        raise ValueError('Not enough unambiguous PDB chains for ligand instances.')
    ligand_map = [dict(source_chain=r['chain'], source_residue=r['residue'],
                       component=r['component'], conditioning_chain=available[i],
                       conditioning_residue=1) for i, r in enumerate(c['ligands'])]
    remap = {(m['source_chain'], m['source_residue'], m['component']): m for m in ligand_map}
    # One ligand per chain makes native per-chain renumbering explicit.
    # Preserve original chain/residue in the map and source.pdb.
    for index, line in enumerate(lines):
        mapped = remap.get((line[21], int(line[22:26]), line[17:20].strip()))
        if mapped:
            lines[index] = line[:21] + mapped['conditioning_chain'] + f"{mapped['conditioning_residue']:4d}" + line[26:]
    conditioned = output / 'conditioning.pdb'
    conditioned.write_text('\n'.join(lines + ['END']) + '\n')
    masks = {r['source_selector']: ','.join(r['conditioning_atoms']) for r in c['protein_motif']}
    for ligand in ligand_map:
        masks[f"{ligand['conditioning_chain']}{ligand['conditioning_residue']}"] = 'ALL'
    spec = dict(input=str(conditioned), length=str(cfg['length']),
                unindex=','.join(r['source_selector'] for r in c['protein_motif']),
                ligand=','.join(dict.fromkeys(r['component'] for r in c['ligands'])),
                select_fixed_atoms=masks,
                run=dict(num_designs=cfg['roots'], num_bins=1, batch_size=1,
                         queues_per_bin=1, timesteps=200, n_recycle=2,
                         seed_base=cfg['seed'], precision='bf16'))
    # JSON is a YAML subset, so no YAML dependency is needed in the GUI bridge.
    atomic(output / 'rfd3.yaml', spec)
    atomic(output / 'case.json', c)
    arms = [dict(designer=d, policy=p, id=d + '-' + p) for d in cfg['designers'] for p in cfg['policies']]
    atomic(output / 'comparison.json', dict(profile=PROFILE, arms=arms, budget=budget(cfg),
           guidance=dict(source=cfg['guidance_source'], residues='mapped motif only', atomic_lock=False),
           ranking=dict(fold_rmsd_lt=2.0, protein_plddt_gt=80.0, motif_rmsd_lt=2.5,
                        every_ligand_centroid_lt=3.0, source_guard_lte=cfg['source_tolerance'],
                        objective='min(max(original_input_motif/2.5,worst_root_pocket_centroid/3)); then min(sum)',
                        rank_predictions='untemplated', reference='immutable root and original source'),
           execution_status='Boltz beta cycling available; other mapped template adapters require native qualification.'))
    files = {name: digest(output / name) for name in ('source.pdb', 'conditioning.pdb', 'rfd3.yaml', 'case.json', 'comparison.json')}
    saved = dict(schema=1, request=cfg, source_revision=catalog()['source_revision'],
                 scope=catalog()['scope'], files=files, budget=budget(cfg), conditioning_ligands=ligand_map)
    atomic(receipt, saved)
    return saved


def verify(output):
    output = Path(output).resolve()
    saved = json.loads((output / 'bundle.json').read_text())
    if saved['request'].get('profile') != PROFILE:
        raise ValueError('Saved beta inputs use an older scoring profile; prepare a new run.')
    normalize(saved['request'])
    for name, checksum in saved['files'].items():
        path = (output / name).resolve()
        if output not in path.parents or digest(path) != checksum:
            raise ValueError('Missing or changed beta input: ' + name)
    return saved
