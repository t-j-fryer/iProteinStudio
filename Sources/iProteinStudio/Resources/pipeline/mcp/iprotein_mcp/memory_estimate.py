"""Advisory, CPU-only estimates. These do not change admission or model settings.

Lab0851 fits median warmed-request peaks. Adding its observed peak residual is a
planning allowance, not a measured maximum or statistical upper confidence bound.
"""
import hashlib
import json
import math
import os
import re
from pathlib import Path

from .common import load_json

PIPELINE = Path(__file__).resolve().parents[2]
# Keep data beside the bridge: native prediction jobs retain this entire
# package even when their installed scientific scripts are an older snapshot.
MODELS_PATH = Path(__file__).with_name('memory_estimate_models.json')

GROUPS = {
    'boltz': 'boltz_app', 'intellifold': 'intellifold_flash_app',
    'intellifold-full': 'intellifold_full_app', 'openfold-3-mlx': 'openfold3_app',
    'protenix-v2': 'protenix_v2_app', 'protenix-mini': 'protenix_mini_app',
    'protenix-constraint-v0.5': 'protenix_constraint_app',
    'esmfold2-full-mlx': 'esmfold2_full_bf16',
    'esmfold2-fast-mlx': 'esmfold2_fast_bf16',
    'esmfold2-600-mlx': 'esm600_standard_bf16',
}


def assembly_shape(job):
    total, copies = 0, 0
    for chain in job.get('chains', []):
        if chain.get('kind', 'protein') != 'protein':
            raise ValueError('Ligand and nucleic-acid RAM is not calibrated by these protein-only fits.')
        sequence = re.sub(r'\s+', '', str(chain.get('sequence', '')))
        count = chain.get('copies', 1)
        if not sequence or type(count) is not int or count < 1:
            raise ValueError('Complete protein sequences and chain-copy counts are needed.')
        total += len(sequence) * count
        copies += count
    if not total:
        raise ValueError('The complete complex size could not be determined.')
    return total, copies


def prediction_estimates(config, models, defaults):
    """One estimate per sequential engine; directory batches reuse each model."""
    from .memory import contract
    admission = contract()
    shapes = [assembly_shape(job) for job in config.get('jobs', [])]
    if not shapes:
        raise ValueError('Read the protein sequences to determine complex size.')
    largest, copies = max(shapes)
    rows = []
    for selected in config.get('predictors', []):
        engine = ('intellifold-full' if selected == 'intellifold' and config.get('intellifold_model') == 'v2'
                  else selected)
        label = {'rfd4': 'RFD4 generation', 'rfd3': 'RFdiffusion3 generation'}.get(engine, engine)
        if engine in GROUPS:
            label = models.get(GROUPS[engine] + '__process_footprint', {}).get('label', label)
        row = dict(engine=engine, label=label, total_aa=largest, chain_copies=copies, estimated_peak_gib=None)
        rows.append(row)
        try:
            if engine not in GROUPS:
                raise ValueError('Whole-process RAM has not been calibrated for this generator.')
            group = GROUPS[engine]
            profile = dict(defaults[engine], **(config.get('prediction_settings') or {}).get(engine, {}))
            samples = config.get('diffusion_samples', 0) or (5 if engine in ('protenix-v2', 'protenix-mini') else 1)
            if samples != 1:
                raise ValueError(f'No matching fit for {samples} diffusion samples; the reference used one.')
            if config.get('template') or config.get('affinity') or config.get('use_potentials'):
                raise ValueError('Structure guidance, affinity and potentials have no matching RAM fit.')
            if engine.startswith('esmfold2-'):
                if os.environ.get('IPROTEINSTUDIO_ESMFOLD2_TRUNK_DTYPE', 'bfloat16') != 'bfloat16':
                    raise ValueError('The fitted ESMFold2 profiles use BF16 trunk weights.')
                if engine == 'esmfold2-600-mlx':
                    pair = (profile.get('chunk_size'), profile.get('cache_limit_mib'))
                    if pair == (32, 512): group = 'esm600_low_memory_bf16'
                    elif pair != (0, 4096):
                        raise ValueError('No matching 600M fit for the selected chunk/cache settings.')
                elif (profile.get('chunk_size'), profile.get('cache_limit_mib')) != (0, 4096):
                    raise ValueError('No matching ESMFold2 fit for the selected chunk/cache settings.')
            reference = defaults[engine]
            for key in ('diffusion_steps', 'recycles', 'msa_depth'):
                if profile.get(key) != reference.get(key):
                    raise ValueError('No matching fit for the selected steps, recycles or MSA depth.')
            if engine not in ('esmfold2-fast-mlx', 'esmfold2-600-mlx'):
                if any(c.get('msa', 'auto') == 'empty' for j in config['jobs'] for c in j['chains']):
                    # Empty designed binders are expected. A target still supplies MSA rows.
                    if all(c.get('msa', 'auto') == 'empty' for j in config['jobs'] for c in j['chains']):
                        raise ValueError('This reference profile used a target MSA; single-sequence memory is uncalibrated.')
            model = models[group + '__process_footprint']
            row.update(label=model['label'], measured_range_aa=[model['min_aa'], model['max_aa']],
                       retrospective_error_percent=model.get('cv_mape_percent'),
                       profile=profile, model_id=model['id'])
            def estimate(size):
                if model['method'] == 'single_size_anchor':
                    if size != model['min_aa']: raise ValueError('Only one measured size is available for this profile.')
                    return model['anchor_median_gib'], 0.0
                a, b = model['coefficients']
                return a + b * (size / 1000) ** model['power'], model['observed_peak_residual_gib']
            values = [estimate(size) for size, _ in shapes]
            workers_default, batch_default = admission.SCHEDULE.get(selected, (1, 1))
            workers = config.get('max_parallel', 0) or workers_default
            batch = config.get('batch_size', 0) or batch_default
            if type(workers) is not int or workers < 1 or type(batch) is not int or batch < 1:
                raise ValueError('Worker count or folds-per-load setting is unavailable.')
            # Match directory bucketing and sequential-per-worker load batches.
            buckets = {}
            for shape, (median, residual) in zip(shapes, values):
                bucket = (0 if selected.startswith('esmfold2-') or selected == 'openfold-3-mlx'
                          else next((b for b in admission.BUCKETS if shape[0] <= b), admission.BUCKETS[-1]))
                buckets.setdefault(bucket, []).append((median, median + residual))
            peaks = []
            for items in buckets.values():
                chunks = [max(x[1] for x in items[i:i+batch]) for i in range(0, len(items), batch)]
                peaks.append(sum(sorted(chunks, reverse=True)[:workers]))
            peak = max(peaks)
            if config.get('memory_scope') == 'resident-design':
                peak = workers * max(median + residual for median, residual in values)
            if not math.isfinite(peak): raise ValueError('The requested size exceeds the numerical estimate range.')
            row.update(estimated_peak_gib=round(peak, 2), median_request_peak_gib=round(max(x[0] for x in values), 2),
                       observed_residual_gib=model.get('observed_peak_residual_gib', 0), workers=workers,
                       extrapolation=any(n < model['min_aa'] or n > model['max_aa'] for n, _ in shapes))
            notes = []
            if row['extrapolation']: notes.append('Outside the measured size range; extrapolated.')
            if workers > 1: notes.append('Concurrent-worker scaling is a planning assumption, not measured validation.')
            row['note'] = ' '.join(notes)
        except (ValueError, KeyError, TypeError) as exc:
            row['note'] = str(exc)
    return rows


def iterative_workload(normalized):
    from .memory import read_template
    args = normalized.get('arguments') or normalized.get('manifest', {}).get('arguments', [])
    def option(name, default=None):
        return args[args.index(name)+1] if name in args else default
    path = normalized.get('template_artifact', {}).get('path') or option('--template-yaml')
    if not path: raise ValueError('The saved design template is unavailable.')
    document = read_template(path)
    maximum = int(option('--binder-max-len', 150))
    chains = []
    for item in document.get('sequences', []):
        if set(item) != {'protein'}: raise ValueError('The protein-only fits do not cover this molecular input.')
        protein = item['protein']
        ids = protein.get('id'); ids = ids if isinstance(ids, list) else [ids]
        for ident in ids:
            seq = protein.get('sequence', '')
            if ident == 'A' and (option('--workflow', 'protein') != 'nanobody' or '--random-binder' in args):
                seq = 'X' * maximum
            chains.append(dict(id=ident, sequence=seq, msa=protein.get('msa', 'auto')))
    if not any(c['id'] == 'A' for c in chains):
        chains.insert(0, dict(id='A', sequence='X'*maximum, msa='empty'))
    engine = option('--predictor', 'boltz')
    def variant(e, model): return 'intellifold-full' if e == 'intellifold' and model == 'v2' else e
    engines = [variant(engine, option('--model', 'v2-flash'))]
    if option('--initialization-method') != 'rfd3':
        engines += [variant(option('--initialization-predictor', engine), option('--initialization-model', option('--model', 'v2-flash')))]
    engines += [variant(e, option('--model', 'v2-flash')) for e in option('--post-predictor', 'none').split(',') if e != 'none']
    workers = option('--max-parallel', '1')
    if workers == 'auto': raise ValueError('Automatic design concurrency has no matching peak-RAM fit.')
    return dict(jobs=[dict(chains=chains)], predictors=list(dict.fromkeys(engines)),
                max_parallel=int(workers), batch_size=1, memory_scope='resident-design',
                diffusion_samples=0 if option('--predictor-samples', 'auto') == 'auto' else int(option('--predictor-samples')),
                prediction_settings=json.loads(option('--prediction-settings-json', '{}')))


def workloads(kind, normalized):
    """Use prepared inputs, including the longest binder, without importing models."""
    if normalized.get('memory_workloads'): return normalized['memory_workloads'], []
    if kind in ('prediction', 'target_prepare', 'desktop_prediction', 'desktop_target_prepare'):
        config = normalized.get('config') or load_json(Path(normalized['output'])/'prediction_config.json')
        return [config], []
    if kind == 'desktop_rfd4':
        cfg = load_json(Path(normalized['output'])/'rfd4_config.json')
        r = cfg['settings']
        if r['task'] not in ('protein', 'monomer', 'nanobody') or r.get('contig') or r.get('annotated_input'):
            raise ValueError('This generation mode has no complete-complex RAM fit yet.')
        length = (r.get('length_plan') or {}).get('maximum', r['length'])
        if r['task'] == 'protein' and not cfg.get('target_sequences'):
            raise ValueError('The complete target assembly size is unavailable.')
        if r['task'] == 'nanobody':
            identities = list(Path(normalized['output']).rglob('framework_identity.json'))
            if not identities: raise ValueError('The complete framework lengths are unavailable.')
            length = max(len(load_json(p)['sequence']) for p in identities)
        chains = [dict(id='A', sequence='X'*length, msa='empty')]
        chains += [dict(id=k, sequence=v, msa=r.get('target_msa', 'auto')) for k,v in cfg.get('target_sequences', {}).items()]
        notes = ['RFD4 generation and sequence-design RAM are not calibrated; the total workflow may peak higher than the prediction estimate.']
        if cfg.get('target_ligands'): raise ValueError('Protein-only fits do not cover the retained ligand.')
        predictors = ['rfd4']
        if r['search'] != 'native' or r.get('assess_native') or r.get('native_search'):
            predictors.append(r['predictor'])
        return [dict(jobs=[dict(chains=chains)], predictors=predictors, max_parallel=1, batch_size=1,
                     diffusion_samples=1)], notes
    if kind == 'desktop_rfdiffusion3':
        cfg = load_json(Path(normalized['output'])/'config/studio_request.json')
        if cfg.get('target_kind') != 'protein' or cfg.get('design_mode') != 'deNovo':
            raise ValueError('No complete-complex RAM fit is available for this RFD3 mode.')
        # Reuse Studio's dependency-free validated structure reader, including
        # all explicitly selected target chains. Never inspect unselected files.
        import importlib.util
        import sys
        path = PIPELINE/'rfd3_scripts/protein_structure.py'
        if not path.is_file(): path = PIPELINE.parent/'rfd3/protein_structure.py'
        spec = importlib.util.spec_from_file_location('studio_ram_protein_structure', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        atoms = module.read_protein_atoms(cfg['target_structure'])
        selected = cfg.get('target_chains') or [cfg['target_chain']]
        chains = []
        for ident in selected:
            count = len({a.residue_number for a in atoms if a.chain == ident})
            if not count: raise ValueError('A selected target chain could not be counted.')
            chains.append(dict(id=ident, sequence='X'*count, msa='auto'))
        chains.append(dict(id='binder', sequence='X'*max(cfg['lengths']), msa='empty'))
        return [dict(jobs=[dict(chains=chains)], predictors=['rfd3'])], []
    if kind in ('desktop_iterative', 'iterative_design'):
        return [iterative_workload(normalized)], ['Initialization, sequence design and overlapping resident stages are not calibrated; estimates describe prediction stages.']
    if kind == 'desktop_iterative_batch':
        return [iterative_workload(child) for child in normalized['engine_campaigns']], ['Design-stage and overlapping resident-model RAM are not calibrated.']
    if kind == 'iterative_batch':
        configs, notes = [], []
        for child in normalized['children']:
            c,n = workloads(child['plan']['kind'], child['plan']['normalized_request']); configs += c; notes += n
        return configs, list(dict.fromkeys(notes))
    raise ValueError('No whole-process RAM model is available for this workflow. Generator allocator anchors are not total RAM estimates.')


def for_plan(plan, machine=None):
    from .memory import contract
    module = contract()
    machine = machine if machine is not None else module.machine_memory()
    total = machine.get('total_bytes')
    result = dict(schema=1, source='Lab0851: M4 Max, 40 GPU cores, 64 GB',
                  total_gib=round(total / 1024**3, 2) if total else None, details=[], notes=[])
    result['estimator_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if not total: result['notes'].append('Installed memory could not be read on this Mac.')
    try:
        data = MODELS_PATH.read_bytes(); pack = json.loads(data)
        result['models_sha256'] = hashlib.sha256(data).hexdigest()
        configs, notes = workloads(plan['kind'], plan['normalized_request'])
        result['notes'] += notes
        defaults = json.loads((PIPELINE/'scripts/prediction_profiles.json').read_text())
        for cfg in configs:
            try: result['details'] += prediction_estimates(cfg, pack['models'], defaults)
            except (ValueError, KeyError, TypeError) as exc: result['notes'].append(str(exc))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result['notes'].append(str(exc))
    details = result['details']
    known = [r['estimated_peak_gib'] for r in details if r.get('estimated_peak_gib') is not None]
    result['estimated_peak_gib'] = max(known) if known else None
    result['partial'] = bool(result['notes'] or any(r.get('estimated_peak_gib') is None for r in details))
    result['largest_complex_aa'] = max((r['total_aa'] for r in details), default=None)
    result['warning'] = bool(result['partial'] or any(r.get('extrapolation') for r in details) or
                             (known and total and max(known) > total / 1024**3 * .8))
    return result


def describe(report):
    """Short, factual text for the native confirmation; no scientific input text."""
    lines = []
    if report.get('total_gib') is not None: lines.append(f"This Mac has {report['total_gib']:.0f} GiB of installed memory.")
    if report.get('largest_complex_aa'):
        lines.append(f"Largest planned protein complex: {report['largest_complex_aa']:,} amino acids, counting every chain copy and the longest configured binder.")
    for row in report['details']:
        label = row.get('label', row['engine'])
        value = row.get('estimated_peak_gib')
        if value is None: lines.append(f"{label}: estimate unavailable. {row['note']}")
        else:
            lines.append(f"{label}: approximately {value:.1f} GiB peak during prediction ({row['total_aa']:,} aa; {row['workers']} worker(s)).")
            lines.append(f"Typical peak {row['median_request_peak_gib']:.1f} GiB, with an allowance for the largest error seen in the benchmark. Measured range: {row['measured_range_aa'][0]}–{row['measured_range_aa'][1]} aa.")
            if row.get('note'): lines.append(row['note'])
    lines += report['notes']
    if not report['details'] and not report['notes']: lines.append('This preparation stage loads no prediction model.')
    lines.append('These are planning estimates from the M4 Max benchmarks, not guaranteed upper limits. Loading, other apps and different Macs can increase memory use; macOS may swap or stop the process.')
    lines.append('Proceed with these saved settings? This choice applies only to this run.')
    return '\n\n'.join(lines)
