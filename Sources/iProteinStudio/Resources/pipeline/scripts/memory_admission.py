"""CPU-only, conservative prediction admission. Never imports an ML framework.

The quadratic/cubic terms follow pair/triangle allocations; runtime overhead is
calibrated against historical *maximum* sampled loading/request footprints.
This is an estimate, not a proof of physical residency or a runtime watchdog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

GIB = 1024 ** 3
DATA = json.loads(Path(__file__).with_name('memory_profiles.json').read_text())
PROFILE_SHA256 = hashlib.sha256(Path(__file__).with_name('memory_profiles.json').read_bytes()).hexdigest()
CONTRACT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
DEFAULTS = json.loads(Path(__file__).with_name('prediction_profiles.json').read_text())
# Directory batches reuse the model sequentially. These mirror predict_batch.
SCHEDULE = {'boltz': (1, 8), 'intellifold': (4, 16),
            'protenix-v2': (1, 8), 'protenix-mini': (1, 8),
            'protenix-constraint-v0.5': (1, 8), 'openfold-3-mlx': (1, 1000000),
            'esmfold2-full-mlx': (1, 100000), 'esmfold2-fast-mlx': (1, 100000)}
BUCKETS = (128, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096)
# Standard-residue heavy atoms (Boltz data/const.py ref_atoms). Unknown design
# residues are charged as tryptophan; one terminal oxygen per chain is included.
HEAVY_ATOMS = dict(zip('ACDEFGHIKLMNPQRSTVWYX',
                      (5,6,8,9,11,4,10,8,9,8,8,8,7,9,11,6,7,7,14,12,14)))


def machine_memory(live=False):
    """Missing counters stay unknown. Never substitute installed RAM for free RAM."""
    def read(args):
        try:
            return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return ''
    total = read(['/usr/sbin/sysctl', '-n', 'hw.memsize']).strip()
    result = {'total_bytes': int(total) if total.isdigit() else None}
    if live:
        pressure = read(['/usr/sbin/sysctl', '-n', 'kern.memorystatus_vm_pressure_level']).strip()
        result['pressure'] = int(pressure) if pressure.isdigit() else None
        vm = read(['/usr/bin/vm_stat'])
        page = re.search(r'page size of (\d+) bytes', vm)
        counts = [re.search(r'^' + key + r':\s+(\d+)\.', vm, re.M)
                  for key in ('Pages free', 'Pages inactive', 'Pages speculative')]
        result['available_bytes'] = (int(page[1]) * sum(int(m[1]) for m in counts)
                                     if page and all(counts) else None)
    return result


def positive(value, label, allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError(f'{label} must be a positive integer.' if not allow_zero
                         else f'{label} must be a nonnegative integer.')
    return value


def job_shape(job):
    chains = job.get('chains')
    if not isinstance(chains, list) or not chains:
        raise ValueError('Read the protein sequences before checking memory.')
    tokens, copies = 0, 0
    for chain in chains:
        # predict_batch renders IDs into YAML. Require one literal chain ID so
        # a list or YAML fragment cannot create extra, uncounted chain copies.
        chain_id = chain.get('id')
        if not isinstance(chain_id, str) or not re.fullmatch(r'[A-Za-z0-9]{1,4}', chain_id):
            raise ValueError('Each protein copy needs its own simple chain ID and sequence before checking memory.')
        if any(c in str(chain.get('msa', 'auto')) for c in '\r\n'):
            raise ValueError('The alignment path must not contain line breaks.')
        if chain.get('kind') != 'protein':
            raise ValueError('A memory estimate is not yet qualified for ligand or nucleic-acid inputs. This run is blocked by the memory check.')
        sequence = re.sub(r'\s+', '', str(chain.get('sequence', ''))).upper()
        if not sequence or not re.fullmatch('[ACDEFGHIKLMNPQRSTVWYX]+', sequence):
            raise ValueError('A complete protein sequence is required for the memory check.')
        count = positive(chain.get('copies', 1), 'Chain copies')
        # Native prediction jobs have one chain per copy; YAML uses ID lists.
        tokens += len(sequence) * count
        copies += count
    if copies > 2:
        raise ValueError('Memory estimates currently cover one or two protein chains. Larger assemblies are blocked until qualified.')
    return tokens


def estimate_job(engine, job, cfg):
    profile = DATA['profiles'].get(engine)
    if profile is None:
        raise ValueError(f'No memory estimate is available for {engine}; this run is blocked.')
    tokens = job_shape(job)
    if tokens > profile['maximum_tokens']:
        raise ValueError(f'{engine}: {tokens:,} residues exceed the memory profile range '
                         f'({profile["maximum_tokens"]:,}). Reduce the input or select another model.')
    settings = {**DEFAULTS[engine], **cfg.get('prediction_settings', {}).get(engine, {})}
    depth = positive(settings['msa_depth'], 'MSA depth', allow_zero=True)
    uses_msa = any(c.get('msa', 'auto') != 'empty' for c in job['chains'])
    if engine != 'esmfold2-fast-mlx' and uses_msa and (depth == 0 or depth > 128):
        raise ValueError(f'{engine}: memory estimates require an explicit MSA cap of at most 128 rows. '
                         'Choose that cap in Prediction Settings, or use single-sequence inputs.')
    if cfg.get('affinity') or cfg.get('use_potentials') or cfg.get('template'):
        raise ValueError('Memory estimates are not yet qualified for affinity, potentials or structure guidance. '
                         'This run is blocked; scientific settings have not been changed.')
    samples = positive(cfg.get('diffusion_samples', 0), 'Diffusion samples', allow_zero=True)
    samples = samples or (5 if engine in {'protenix-v2', 'protenix-mini'} else 1)
    # The calibration used one sample. Charging the entire worker per sample is
    # deliberately conservative; it does not assume upstream chunking saves RAM.
    raw = (profile['base_gib'] + profile['quadratic_gib'] * tokens ** 2
           + profile['cubic_bytes'] * tokens ** 3 / GIB)
    atoms = sum((sum(HEAVY_ATOMS[a] for a in re.sub(r'\s+', '', c['sequence']).upper()) + 1)
                * c.get('copies', 1) for c in job['chains'])
    # Seven is below the heavy-atom density of every calibration protein.
    # Scale the whole envelope for richer sequences instead of assuming atom
    # workspace stays constant. This is a conservative policy, not a new timing.
    atom_factor = max(1.0, (atoms / (7.0 * tokens)) ** 2)
    required = (raw * atom_factor * DATA['margin'] + DATA['overhead_gib']) * samples
    return {'engine': engine, 'name': job.get('name', 'protein'), 'tokens': tokens,
            'samples': samples, 'heavy_atoms': atoms, 'estimated_gib': required}


def _assess(config, machine=None, live=False):
    """Same decision for preview, saved plans and dispatch; input is never mutated."""
    machine = machine if machine is not None else machine_memory(live)
    result = {'policy': DATA['policy'], 'profile_sha256': PROFILE_SHA256, 'contract_sha256': CONTRACT_SHA256,
              'status': 'blocked', 'estimated_gib': None,
              'budget_gib': None, 'total_gib': None, 'details': [], 'message': ''}
    try:
        if not machine.get('total_bytes'):
            raise ValueError('Studio could not read this Mac’s installed memory. The run is blocked; retry when system readings are available.')
        total = positive(machine.get('total_bytes'), 'Installed memory') / GIB
        reserve = max(4.0, total * 0.20)
        budget = max(0.0, total - reserve)
        result.update(total_gib=round(total, 2), budget_gib=round(budget, 2))
        if live:
            if machine.get('available_bytes') is None:
                raise ValueError('Studio could not read available memory. The run has not started; retry when system readings are available.')
            available = positive(machine.get('available_bytes'), 'Available memory', allow_zero=True) / GIB
            if machine.get('pressure') not in {1, 2, 4}:
                raise ValueError('Memory pressure could not be read. The run has not started; retry after system readings recover.')
            if machine['pressure'] != 1:
                raise ValueError('macOS reports elevated memory pressure. Close other memory-intensive apps and retry.')
            budget = min(budget, max(0.0, available - 2.0))
            result['budget_gib'] = round(budget, 2)
        jobs = config.get('jobs')
        if not isinstance(jobs, list) or not jobs:
            raise ValueError('Read the protein sequences before checking memory.')
        engines = config.get('predictors')
        if not isinstance(engines, list) or not engines:
            raise ValueError('Select a prediction model before checking memory.')
        parallel = positive(config.get('max_parallel', 0), 'Workers', allow_zero=True)
        configured_batch = positive(config.get('batch_size', 0), 'Batch size', allow_zero=True)
        peak = 0.0
        for selected in engines:
            engine = 'intellifold-full' if selected == 'intellifold' and config.get('intellifold_model') == 'v2' else selected
            default_workers, default_batch = SCHEDULE.get(selected, (1, 1))
            if selected == 'boltz' and config.get('use_potentials'):
                default_workers, default_batch = 2, 4
            workers, batch = parallel or default_workers, configured_batch or default_batch
            groups = {}
            for job in jobs:
                item = estimate_job(engine, job, config)
                # Keep the scheduler's exact bucket ordering; batches are not a
                # tensor batch. Models from separate engines run sequentially.
                bucket = 0 if selected.startswith('esmfold2-') or selected == 'openfold-3-mlx' else next((b for b in BUCKETS if item['tokens'] <= b), BUCKETS[-1])
                groups.setdefault(bucket, []).append(item)
            engine_peak = 0.0
            for items in groups.values():
                chunks = [max(x['estimated_gib'] for x in items[i:i + batch])
                          for i in range(0, len(items), batch)]
                engine_peak = max(engine_peak, sum(sorted(chunks, reverse=True)[:workers]))
            if config.get('memory_scope') == 'resident-design':
                # One synthetic maximum-length job represents every trajectory,
                # not a single queued item. Explicit parallelism still applies.
                engine_peak = workers * max(item['estimated_gib'] for items in groups.values() for item in items)
            # Design stages can retain a predictor while a checker or sequence
            # designer runs. Charge all selected models, plus a CPU allowance;
            # do not assume teardown that has not been demonstrated here.
            peak = peak + engine_peak if config.get('memory_scope') == 'resident-design' else max(peak, engine_peak)
            result['details'].append({'engine': engine, 'estimated_gib': round(engine_peak, 2),
                                      'workers': workers, 'largest_input': max(job_shape(j) for j in jobs)})
        if config.get('memory_scope') == 'resident-design':
            peak += 4.0  # Policy allowance, not a measured designer benchmark.
        result['estimated_gib'] = round(peak, 2)
        result['status'] = 'blocked' if peak > budget else ('warning' if peak > budget * 0.8 else 'allowed')
        summary = f'Estimated model memory: {peak:.1f} GiB; budget: {budget:.1f} GiB on this {total:.0f} GiB Mac.'
        result['message'] = summary + (' Reduce the input, worker count or samples, or select another model.'
                                      if result['status'] == 'blocked' else
                                      ' Close memory-intensive apps before starting.' if result['status'] == 'warning' else
                                      ' Includes headroom; checked again when the job starts.')
    except (ValueError, TypeError, KeyError) as exc:
        result['message'] = str(exc)
    return result


def apply_policy(result, policy):
    if policy not in ('enforce', 'override'):
        raise ValueError('memory_policy must be enforce or override.')
    result = {**result, 'memory_policy': policy}
    if policy == 'override':
        result.update(status='overridden', would_be_status=result['status'],
                      original_message=result['message'],
                      message='Memory check overridden by user. ' + result['message'])
    return result


def assess(config, machine=None, live=False):
    return apply_policy(_assess(config, machine, live), config.get('memory_policy', 'enforce'))


def require(config, live=False):
    config = {**config, 'memory_policy': os.environ.get('IPROTEINSTUDIO_MEMORY_POLICY', config.get('memory_policy', 'enforce'))}
    result = assess(config, live=live)
    if result['status'] == 'blocked':
        raise ValueError(result['message'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    try:
        result = assess(json.loads(args.config.read_text()), live=args.live)
    except (OSError, ValueError) as exc:
        result = {'status': 'blocked', 'message': f'Could not check memory: {exc}'}
    print(json.dumps(result, allow_nan=False))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
