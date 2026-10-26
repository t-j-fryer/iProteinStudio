"""Bounded managed RFD3 beta pilot and reproducible downstream workbench."""
import csv
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from .contract import atomic, digest, prepare, verify


def rank_roots(records):
    if not records:
        raise ValueError('No generated roots to rank.')
    for record in records:
        for value in (record['candidate_motif_rmsd_to_input'], record['input_motif']['rmsd']):
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError('Root ranking requires finite, nonnegative motif RMSDs.')
    ranked = sorted(records, key=lambda r: (r['candidate_motif_rmsd_to_input'], r['input_motif']['rmsd'], r['id']))
    return [{**record, 'motif_rank': index} for index, record in enumerate(ranked, 1)]


def rfd3_view(root, output):
    """Private overlay atop the broker's retained runtime; never edit installation."""
    source, overlay, view = root / 'rfd3', root / 'rfd3_overlay', output / '.rfd3_beta'
    code = {}
    for base in (source, overlay):
        for path in list(base.glob('*.py')) + list((base / 'scripts').rglob('*.py')):
            code[str(path.relative_to(base))] = path
    identity = {name: digest(path) for name, path in code.items()}
    marker = view / 'beta_code.json'
    if marker.exists():
        if json.loads(marker.read_text()) != identity or any(digest(view / n) != h for n, h in identity.items()):
            raise ValueError('The retained beta RFD3 code changed.')
        return view
    view.mkdir(parents=True, exist_ok=True)
    for name, path in code.items():
        dest = view / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    for path in source.iterdir():
        if path.name in {'scripts', '.git', '__pycache__'} or path.suffix == '.py': continue
        dest = view / path.name
        if not dest.exists(): dest.symlink_to(path.resolve())
    # Script-local assets also remain the retained runtime's exact artifacts.
    for path in (source / 'scripts').iterdir():
        dest = view / 'scripts' / path.name
        if not dest.exists(): dest.symlink_to(path.resolve())
    atomic(marker, identity)
    return view


def run(config, output):
    root = Path(os.environ['NANOHUNTER_ROOT'])
    output = Path(output).resolve()
    raw = json.loads(Path(config).read_text())
    saved = prepare(output / 'bundle', raw)
    cfg = saved['request']
    print('MOTIFBETA|prepared|' + cfg['case_id'], flush=True)
    if cfg['stage'] == 'prepare':
        atomic(output / 'status.json', dict(state='prepared', inference=False, bundle='bundle',
               message='Exact motif/ligand inputs and comparison design saved. No models were run.'))
        return
    view = rfd3_view(root, output)
    command = [str(root / 'rfd3/.venv/bin/python'), str(view / 'scripts/design_from_yaml.py'),
               str(output / 'bundle/rfd3.yaml'), '--output', str(output / 'generation'), '--name', cfg['case_id']]
    log = output / 'rfd3.log'
    with log.open('a') as stream:
        subprocess.run(command, cwd=view, stdout=stream, stderr=subprocess.STDOUT, check=True)
    from .geometry import freeze_root, input_motif_report
    table = output / 'generation/rfd3/backbone_metrics.csv'
    rows = list(csv.DictReader(table.open()))
    if len(rows) != cfg['roots']:
        raise ValueError('RFD3 returned an unexpected root count.')
    refs = []
    for row in rows:
        metadata = {k: json.loads(row[k]) for k in ('diffused_index_map', 'motif_fixed_atoms', 'ligand_instance_map')}
        reference = output / 'references' / (row['design'] + '.json')
        freeze_root(output / 'bundle', Path(row['backbone_pdb']), metadata, reference)
        report = input_motif_report(reference, row['backbone_pdb'])
        # RFD3 writes fixed guide atoms into its exported PDB. Preserve the
        # pre-copy placement diagnostic so exported exact matches cannot hide
        # differences between proposed scaffolds.
        pre_copy = row.get('motif_candidate_rmsd_to_input')
        if pre_copy in (None, '', 'None'):
            raise ValueError('RFD3 lacks pre-copy input-motif RMSD; regenerate with the current overlay.')
        value = float(pre_copy)
        if not math.isfinite(value) or value < 0:
            raise ValueError('Invalid RFD3 input-motif placement RMSD.')
        refs.append(dict(id=row['design'], reference=str(reference), backbone=row['backbone_pdb'],
                         input_motif=report, candidate_motif_rmsd_to_input=value))
    refs = rank_roots(refs)
    atomic(output / 'roots.json', refs)
    atomic(output / 'root_ranking.json', dict(ranked_roots=refs, best_root=refs[0]['id'],
        ranking='candidate selected-atom RMSD to original input before fixed-atom copy; exported RMSD as tie-break',
        interpretation='Geometry ranking only; all requested roots remain in the comparison.'))
    if cfg['stage'] == 'cycles':
        from .cycling import run as cycle
        result = cycle(root, output, cfg, refs)
        atomic(output / 'status.json', dict(state='cycles_complete', checked=result['checked'],
               independent_validation=False, message='Beta cycling complete. Search candidates require an untemplated check from a different model family.'))
        return
    atomic(output / 'status.json', dict(state='backbones_complete', roots=len(refs),
           inference=True, sequence_design=False, independent_validation=False,
           message='RFD3 pilot complete. Roots are unvalidated; use the workbench to qualify templates and designers.'))
    print('MOTIFBETA|backbones_complete|' + str(len(refs)), flush=True)
