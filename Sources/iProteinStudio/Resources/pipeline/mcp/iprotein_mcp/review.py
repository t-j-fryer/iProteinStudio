"""Bounded retrospective review. Raw results and their recorded verdicts stay immutable."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import statistics
import zipfile

from . import catalog, exports
from .common import StudioError, agent_root, atomic_json, canonical_digest, file_digest, runtime_root

PRIORITY = {'complex_reprediction': 0, 'complexReprediction': 0, 'design': 1,
            'designed_complex': 1, 'complex': 1, 'prediction': 2, 'selection_oracle': 0,
            'binder_alone': 4, 'starting_structure': 99}


def _snapshot(run_id, snapshot_sha256=None):
    rows = exports._index(run_id)
    digest = canonical_digest(rows)
    if snapshot_sha256 is not None and digest != snapshot_sha256:
        raise StudioError('Results changed; obtain a fresh candidate snapshot.')
    return rows, digest


def _scores(artifact):
    scores = {k: v for k, v in artifact.get('metrics', {}).items()
              if type(v) in (int, float) and math.isfinite(v)}
    for key in ('plddt', 'complex_plddt', 'binder_plddt'):
        if key in scores and 0 <= scores[key] <= 1.000001: scores[key] *= 100
    # The bridge normalizes legacy fractional ligand confidence at ingestion;
    # only combine scores carried by this very same assessment.
    if 'ligand_plddt' in scores:
        plddt = scores['ligand_plddt']
        if 0 <= plddt <= 1.000001: plddt *= 100
        if 0 <= plddt <= 100:
            scores['ligand_plddt'] = plddt
            probability = scores.get('affinity_probability_binary', scores.get('pbind'))
            if probability is not None and 0 <= probability <= 1:
                scores['boltz_combined_score'] = probability + plddt / 100
    return scores


def _primary(record, predictor=None, role=None):
    artifacts = [a for a in record['artifacts'] if a.get('path') and
                 a.get('role') != 'starting_structure' and
                 Path(a['path']).suffix.lower() in {'.pdb', '.cif', '.mmcif'} and
                 (predictor is None or a.get('predictor') == predictor) and
                 (role is None or a.get('role') == role)]
    return sorted(artifacts, key=lambda a: (PRIORITY.get(a.get('role'), 10), a.get('path', '')))


def _spatial_rows(job_id, run_id, snapshot):
    if job_id is None: return {}
    from .broker import load_state, state_path
    from .common import load_json
    state = load_state(job_id)
    plan = load_json(state_path(job_id).parent / 'plan.json')
    n = plan['normalized_request']
    if plan['kind'] != 'results_spatial' or n['run_id'] != run_id or n['snapshot_sha256'] != snapshot:
        raise StudioError('Spatial analysis belongs to a different run or results snapshot.')
    if state['status'] != 'completed':
        raise StudioError('Spatial analysis must complete before applying its filter. Inspect job_status; resume interrupted work.')
    path = Path(n['output']) / 'assessment.json'
    saved = load_json(path)
    rows = saved.get('rows', [])
    if canonical_digest(rows) != saved.get('rows_sha256') or saved.get('plan_sha256') != plan['sha256']:
        raise StudioError('Spatial assessment failed integrity validation.')
    for row in rows:
        receipt = row.get('receipt')
        if receipt and file_digest(Path(receipt)) != row.get('receipt_sha256'):
            raise StudioError('Spatial receipt changed; resume analysis to verify cached work.')
    return {r['id']: r for r in rows}


def _review(run_id, metric=None, mode='all', rules=None, descending=True,
            max_per_family=None, predictor=None, role=None, snapshot_sha256=None,
            spatial_job_id=None):
    records, snapshot = _snapshot(run_id, snapshot_sha256)
    spatial = _spatial_rows(spatial_job_id, run_id, snapshot)
    rows, medians, available = [], {}, set()
    ligand = False
    for record in records:
        assessments = _primary(record, predictor, role)
        values, sources = {}, {}
        for artifact in assessments:
            scores = _scores(artifact)
            ligand |= any(k in scores for k in ('ligand_plddt', 'boltz_combined_score', 'affinity_probability_binary'))
            source = {k: artifact.get(k) for k in ('path', 'path_sha256', 'predictor', 'role', 'prediction_context')}
            for key, value in scores.items():
                if key not in values: values[key], sources[key] = value, source
            if record.get('cycle') is not None:
                series = (record['cycle'], artifact.get('predictor'), artifact.get('role'), artifact.get('prediction_context'))
                for key, value in scores.items():
                    medians.setdefault((series, key), {}).setdefault(record['candidate_id'], value)
        row = {k: record.get(k) for k in ('candidate_id', 'run_id', 'group_id', 'variant_id', 'cycle', 'sequence', 'is_hit')}
        row.update(design_name=record['group_id'] + ' / ' + record['variant_id'], metrics=values, metric_sources=sources)
        if spatial_job_id:
            match = spatial.get(record['candidate_id'])
            # An unselected, failed or absent pose cannot pass the optional filter.
            if not match or match.get('error') or match.get('passed') is not True: continue
            row['spatial'] = match
            for key in ('minimum_distance', 'maximum_distance'):
                if type(match.get(key)) in (int, float): values['spatial_' + key] = match[key]
            sasa = match.get('sasa') or {}
            for key in ('buried_percent', 'isolated_sasa_a2', 'complex_sasa_a2'):
                if type(sasa.get(key)) in (int, float): values['ligand_' + key] = sasa[key]
        available.update(values)
        rows.append(row)
    if metric is None:
        metric = 'boltz_combined_score' if ligand else next((k for k in ('ipsae_min', 'iptm', 'ptm', 'plddt') if k in available), None)
        metric = metric or next(iter(sorted(available)), None)
    rules = rules or []
    if mode not in ('all', 'saved', 'custom'): raise StudioError('Unknown hit selection mode.')
    if mode == 'custom' and not rules: raise StudioError('Custom mode needs at least one metric rule.')
    if max_per_family is not None and (type(max_per_family) is not int or not 1 <= max_per_family <= 10000):
        raise StudioError('Family limit must be a positive integer, at most10000.')
    for rule in rules:
        if rule.get('comparison') not in ('>=', '<=', '>', '<') or type(rule.get('threshold')) not in (int, float) or not math.isfinite(rule['threshold']):
            raise StudioError('Each rule needs a finite threshold and supported comparison.')
    def passes(row):
        if mode == 'saved': return row['is_hit'] is True
        if mode != 'custom': return True
        for rule in rules:
            value = row['metrics'].get(rule['metric']); limit = rule['threshold']
            if value is None: return False
            if not {'>=': value >= limit, '<=': value <= limit, '>': value > limit, '<': value < limit}[rule['comparison']]: return False
        return True
    selected = [r for r in rows if passes(r)]
    selected.sort(key=lambda r: (r['metrics'].get(metric) is None,
        (-1 if descending else 1) * r['metrics'].get(metric, 0), r['candidate_id']))
    counts, capped = {}, []
    for row in selected:
        family = (row['run_id'], row['group_id'])
        if max_per_family is not None and counts.get(family, 0) >= max_per_family: continue
        capped.append(row); counts[family] = counts.get(family, 0) + 1
    cycles = [dict(cycle=series[0], predictor=series[1], role=series[2], prediction_context=series[3],
                   median=statistics.median(values.values()), count=len(values))
              for (series, key), values in sorted(medians.items(), key=lambda p: repr(p[0])) if key == metric]
    cycles.sort(key=lambda row: (str(row['predictor']), str(row['role']), str(row['prediction_context']), float(row['cycle'])))
    units = {key: '0–100' for key in ('plddt', 'complex_plddt', 'binder_plddt', 'ligand_plddt') if key in available}
    units.update({key: unit for key, unit in {'boltz_combined_score': '0–2', 'spatial_minimum_distance': 'Å',
        'spatial_maximum_distance': 'Å', 'ligand_buried_percent': '%', 'ligand_isolated_sasa_a2': 'Å²',
        'ligand_complex_sasa_a2': 'Å²'}.items() if key in available})
    return dict(schema_version=1, run_id=run_id, snapshot_sha256=snapshot, metric=metric,
        available_metrics=sorted(available), metric_units=units, cycle_medians=cycles, mode=mode, total_candidates=len(records),
        selected_count=len(capped), candidates=capped,
        interpretation='Retrospective selection; saved verdicts are unchanged. Medians include all proposals with recorded cycles, separated by predictor/role/context. Metric sources are explicit; missing values never pass rules. Computational scores are not experimental binding evidence.')


def results_review(limit=50, offset=0, **request):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise StudioError('Invalid review page range.')
    if offset and not request.get('snapshot_sha256'):
        raise StudioError('Pagination after the first page requires snapshot_sha256.')
    result = _review(**request)
    rows = result['candidates']; result['candidates'] = rows[offset:offset + limit]
    result.update(offset=offset, next_offset=offset+limit if offset+limit < len(rows) else None)
    return result


def _archive(files, count):
    if sum(len(data) for data in files.values()) > exports.MAX_EXPORT_BYTES:
        raise StudioError('Export exceeds64 MiB of uncompressed content; narrow the selection.')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    data = stream.getvalue()
    if len(data) > exports.MAX_EXPORT_BYTES: raise StudioError('Export exceeds64 MiB; narrow the selection.')
    digest = hashlib.sha256(data).hexdigest(); directory = agent_root() / 'exports'; directory.mkdir(exist_ok=True)
    path = directory / (digest + '.zip')
    if path.exists() and file_digest(path) != digest: raise StudioError('Saved export checksum mismatch.')
    if not path.exists():
        import tempfile
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
            handle.write(data); temporary = Path(handle.name)
        temporary.replace(path)
    return dict(schema_version=1, export_sha256=digest, bytes=len(data), candidate_count=count,
                uri='iprotein://exports/' + digest, format='zip', local_path=str(path),
                retrieval='Use export_read, decode base64, verify the complete SHA-256, then extract.')


def results_review_export(**request):
    result = _review(**request)
    columns = ['design_name', 'sequence', 'run_id', 'group_id', 'candidate_id', 'variant_id', 'cycle', 'is_hit']
    metrics = result['available_metrics']; stream = io.StringIO(newline=''); writer = csv.writer(stream)
    writer.writerow(columns + metrics)
    def safe(value):
        text = '' if value is None else str(value)
        return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text
    for row in result['candidates']:
        writer.writerow([safe(row.get(k)) for k in columns] + [row['metrics'].get(k, '') for k in metrics])
    return _archive({'designs.csv': stream.getvalue().encode('utf-8'),
                     'review.json': json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode()}, result['selected_count'])


def viewer_script_export(run_id, candidate_id, snapshot_sha256, artifact_index=0, emphasized_chains=''):
    records, _ = _snapshot(run_id, snapshot_sha256)
    record = next((r for r in records if r['candidate_id'] == candidate_id), None)
    if record is None: raise StudioError('Unknown candidate ID.')
    if type(artifact_index) is not int or not 0 <= artifact_index < len(record['artifacts']): raise StudioError('Invalid artifact index.')
    artifact = record['artifacts'][artifact_index]; path = Path(artifact.get('path', ''))
    if path.suffix.lower() not in ('.pdb', '.cif', '.mmcif'): raise StudioError('Choose a coordinate artifact.')
    source = catalog.resolve_run(record['run_id']) / path
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != artifact['path_sha256']: raise StudioError('Coordinates changed.')
    chains = re.split(r'[,\s]+', emphasized_chains.strip()) if emphasized_chains.strip() else []
    if not all(re.fullmatch(r'[A-Za-z0-9_]+', c) for c in chains): raise StudioError('Invalid chain IDs.')
    # This template is checked byte-for-byte against the native Swift writer.
    template = (Path(__file__).resolve().parents[1] / 'templates/chimerax_manuscript_v1.py.txt').read_text()
    payload = json.dumps(dict(source='structure' + source.suffix.lower(), sha256=artifact['path_sha256'], emphasized_chains=chains), sort_keys=True)
    script = template.replace('__STUDIO_CONFIG_JSON_LITERAL__', json.dumps(payload))
    # Portable ZIP: resolve the sibling structure beside this Python script.
    script = script.replace("if hashlib.sha256(Path(cfg['source']).read_bytes())", "cfg['source'] = str(Path(__file__).resolve().parent / cfg['source'])\nif hashlib.sha256(Path(cfg['source']).read_bytes())", 1)
    return _archive({'manuscript_style.py': script.encode(), 'structure' + source.suffix.lower(): data,
                     'source.json': json.dumps(dict(candidate=record, artifact_index=artifact_index), sort_keys=True).encode()}, 1)


def _helper(path=None):
    path = path or Path(__file__).resolve().parents[2] / 'scripts/results_spatial.py'
    spec = importlib.util.spec_from_file_location('_studio_spatial_review', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def results_spatial_plan(run_id, candidate_ids, snapshot_sha256, policy, artifact_index=0):
    from .plans import _persist, _script_provenance
    records, _ = _snapshot(run_id, snapshot_sha256)
    selected = {r['candidate_id']: r for r in records}
    if not 1 <= len(candidate_ids) <= 100 or len(set(candidate_ids)) != len(candidate_ids) or any(i not in selected for i in candidate_ids):
        raise StudioError('Select1–100 distinct candidate IDs from the current snapshot.')
    helper = _helper()
    try: helper.validate(policy)
    except (ValueError, KeyError, TypeError) as exc: raise StudioError('Invalid spatial policy: ' + str(exc)) from exc
    units, sources = [], []
    for identity in candidate_ids:
        row = selected[identity]
        if not 0 <= artifact_index < len(row['artifacts']): raise StudioError('Invalid artifact index.')
        artifact = row['artifacts'][artifact_index]
        if Path(artifact.get('path', '')).suffix.lower() not in {'.pdb', '.cif', '.mmcif'} or artifact.get('role') in {'binder_alone', 'starting_structure'}:
            raise StudioError('Select an assessed complex coordinate artifact.')
        source = catalog.resolve_run(row['run_id']) / artifact['path']; checksum = artifact['path_sha256']
        recorded = helper.geometry(source, checksum) if policy['mode'] == 'ligand' else None
        if policy.get('requireGeometry') and recorded is None: raise StudioError('Required exact-pose ligand geometry receipt is missing.')
        if recorded: sources.append(Path(recorded['receipt']))
        sources.append(source)
        units.append(dict(id=identity, source_item_id=str(artifact_index), source=str(source), source_stamp=checksum,
                          geometry=recorded))
    pipeline = Path(__file__).resolve().parents[2]
    python = runtime_root() / 'venvs/NanoHunter_boltz/bin/python'
    if not python.is_file(): raise StudioError('Install Boltz-2 for the Gemmi/RDKit CPU analysis environment; no predictor will run.')
    n = dict(run_id=run_id, snapshot_sha256=snapshot_sha256, policy=policy, units=units,
             pipeline_snapshot=str(pipeline), python=str(python), analysis_engine='boltz')
    key = canonical_digest(n); n['output'] = str(agent_root() / 'reviews' / key)
    provenance = _script_provenance([Path(helper.__file__), pipeline / 'scripts/nise/atom_geometry.py', python] + sources)
    return _persist('results_spatial', Path(run_id).parts[0], n,
                    [str(python), '-B', str(helper.__file__), 'run', '<immutable-spatial-request.json>'], 'cpu_analysis', provenance)


def execute_spatial(job_id, plan):
    from . import broker
    n = plan['normalized_request']; output = Path(n['output']); output.mkdir(parents=True, exist_ok=True)
    frozen = Path(plan['code_snapshot']['path']); helper_path = frozen / 'scripts/results_spatial.py'
    helper = _helper(helper_path)
    def verify_sources():
        for unit in n['units']:
            if file_digest(Path(unit['source'])) != unit['source_stamp']: raise StudioError('Spatial pose changed after preflight.')
            recorded = helper.geometry(Path(unit['source']), unit['source_stamp']) if n['policy']['mode'] == 'ligand' else None
            if recorded != unit['geometry']: raise StudioError('Recorded geometry changed after preflight.')
    verify_sources()
    request = dict(policy=n['policy'], policy_sha256=canonical_digest(n['policy']), cache=str(output / 'cache'), units=n['units'])
    request_path = output / 'request.json'; atomic_json(request_path, request)
    broker._update(job_id, output_root=str(output), stage='spatial_review', message='Reviewing exact saved poses on CPU; no prediction.')
    command = ['/usr/bin/caffeinate', '-dimsu', n['python'], '-B', str(helper_path), 'run', str(request_path)]
    env = broker.stable_environment()
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS'): env[key] = '1'
    code = broker._run_logged(job_id, command, runtime_root(), env)
    if code: return code
    verify_sources()
    rows = {}
    for line in (broker.state_path(job_id).parent / 'pipeline.log').read_text().splitlines():
        try: row = json.loads(line)
        except ValueError: continue
        if isinstance(row, dict) and row.get('id') in {u['id'] for u in n['units']} and row.get('policy_sha256') == request['policy_sha256']:
            if row.get('receipt'): row['receipt_sha256'] = file_digest(Path(row['receipt']))
            rows[row['id']] = row
    if len(rows) != len(n['units']): raise StudioError('Spatial analysis did not produce a receipt or explicit error for every selected pose.')
    rows = [rows[k] for k in sorted(rows)]
    atomic_json(output / 'assessment.json', dict(plan_sha256=plan['sha256'], rows=rows, rows_sha256=canonical_digest(rows)))
    return 0


def memory_estimate(plan_id, plan_sha256):
    from .plans import load_plan
    from .memory_estimate import for_plan
    plan = load_plan(plan_id, plan_sha256)
    return dict(plan_id=plan_id, plan_sha256=plan_sha256, estimate=for_plan(plan),
                interpretation='Measured M4 Max profiles and explicit unknowns; estimates are not installed-RAM guarantees or permission to override admission.')
