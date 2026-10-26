"""Resident, full-schedule RFD4 generation inside the shared Studio job lease."""
import json
import os
from pathlib import Path
import sys
import time
from .contract import atomic, fixed, seal, sha, verify, residue_letter


def call(pipe, config, seed, directory, optimized):
    import numpy as np
    import torch
    from rfd4_proteina_prep import prepare_cif, write_cif
    directory = Path(directory)
    done = directory / 'completed.json'
    identity = dict(seed=seed, settings=config['settings'], input_sha256=sha(config['annotated_cif']), optimized=optimized)
    fixed(directory / 'identity.json', identity)
    if done.exists(): return verify(done)
    from .budget import checkpoint
    checkpoint()
    attempt = directory / ('attempt_' + str(time.time_ns()))
    attempt.mkdir(parents=True)
    cfg = config['settings']
    features, atoms = prepare_cif(config['annotated_cif'], seed=cfg['seed'], device='mps')
    keys = ['padding_mask', 'is_in_context_conditioning', 'supports_local_latent', 'token_type', 'atom37_mask']
    conditioning = {k: v for k, v in features.items() if k not in keys + ['coords_nm']}
    args = {k: features[k] for k in keys}
    if cfg['task'] in ('partial', 'inverse'):
        args['coords_nm'] = features['coords_nm']
        start = 0.0 if cfg['task'] == 'inverse' else 1.0 - cfg['partial_fraction']
        args.update(partial_t_bb_ca=start, partial_t_local_latents=start,
                    inverse_folding=cfg['task'] == 'inverse')
    steps = []
    memory = []
    def progress(pipeline, index, timestep, values):
        steps.append(index)
        memory.append(torch.mps.driver_allocated_memory())
        atomic(directory / 'progress.json', dict(step=index+1, seed=seed))
        return values
    adapter = None
    if optimized:
        from .metal import Adapter
        adapter = Adapter(pipe, 'pair')
    torch.mps.synchronize()
    started = time.perf_counter()
    try:
        result = pipe(**args, conditioning_features=conditioning, num_designs_per_prompt=1,
                      generator=[torch.Generator('cpu').manual_seed(seed)], callback_on_step_end=progress)
        torch.mps.synchronize()
        seconds = time.perf_counter() - started
    finally:
        if adapter is not None: adapter.restore()
    if not steps or steps != list(range(len(steps))): raise ValueError('RFD4 sampling did not complete a contiguous trajectory.')
    if cfg['task'] != 'partial' and len(steps) != len(pipe.config.recycle_depths):
        raise ValueError('RFD4 sampling stopped before the released schedule completed.')
    arrays = {k: v.detach().float().cpu().numpy() if v.is_floating_point() else v.detach().cpu().numpy()
              for k, v in result.items() if isinstance(v, torch.Tensor)}
    if arrays['coords_nm'].shape[0] != 1 or not all(np.isfinite(v).all() for v in arrays.values()):
        raise ValueError('RFD4 output cardinality or finite-value audit failed.')
    if cfg['task'] == 'inverse':
        difference = float((result.bb_ca - features['coords_nm'][..., 1, :]).abs().max().item() * 10)
        if difference >= 1e-4: raise ValueError('Inverse folding did not preserve terminal C-alpha coordinates.')
    np.savez_compressed(attempt / 'tensors.npz', **arrays)
    structure = attempt / 'generated.cif'
    write_cif(result, features, atoms, structure)
    native_structure = structure
    if cfg['task'] in ('protein', 'nanobody'):
        from .search_engine import canonical_protein
        structure = canonical_protein(structure, config, attempt / 'roles.pdb')
    elif cfg['task'] == 'ligand':
        from .inputs import ligand_pdb
        structure = ligand_pdb(structure, attempt / 'roles.pdb')
    from protein_structure import read_protein_atoms
    exported = read_protein_atoms(structure)
    if not exported or not np.isfinite([[a.x, a.y, a.z] for a in exported]).all():
        raise ValueError('RFD4 structure export is empty or nonfinite.')
    sequences = {}
    for atom in exported:
        if atom.atom == 'CA': sequences[atom.chain] = sequences.get(atom.chain, '') + residue_letter(atom.residue)
    if not sequences or any(set(seq) - set('ACDEFGHIKLMNPQRSTVWY') for seq in sequences.values()):
        raise ValueError('RFD4 did not export complete standard protein sequences.')
    from .targets import target_sequences
    if any(sequences.get(chain) != sequence for chain, sequence in target_sequences(config).items()):
        raise ValueError('Generated target sequence or chain identity differs from the frozen target.')
    if cfg['task'] == 'monomer' and (len(sequences) != 1 or len(next(iter(sequences.values()))) != cfg['length']):
        raise ValueError('Generated monomer length or chain count differs from the request.')
    fasta = attempt / 'sequences.fasta'
    fasta.write_text(''.join(f'>seed_{seed}|chain_{chain}\n{seq}\n' for chain, seq in sequences.items()))
    record = dict(id=f'seed_{seed}', family=f'seed_{seed}', seed=seed, structure=str(structure),
                  structure_sha256=sha(structure), sequences=sequences, sampler_seconds=seconds,
                  schedule_steps=len(steps), model_recycle_depths=list(pipe.config.recycle_depths),
                  timing_scope='Synchronized model call including progress and sampled memory; excludes preparation, export and loading',
                  sampled_max_driver_bytes=max(memory), optimized=optimized,
                  tensors=str(attempt / 'tensors.npz'), generation_is_validation=False)
    record['native_structure'] = str(native_structure)
    atomic(attempt / 'measurement.json', record)
    seal(done, record, [directory / 'identity.json', structure, native_structure, fasta, attempt / 'tensors.npz', attempt / 'measurement.json'])
    return record


def main(config_path, first_only=False):
    from .prepare import runtime
    config = json.loads(Path(config_path).read_text())
    output = Path(config['output'])
    if not (output / 'studio_job.json').is_file(): raise RuntimeError('RFD4 generation requires a managed Studio job.')
    root = Path(os.environ['NANOHUNTER_ROOT'])
    code = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(code / 'rfd3_scripts'))
    sys.path.insert(0, str(root / 'rfd3_scripts'))
    os.environ.update(PYTORCH_ENABLE_MPS_FALLBACK='0', HF_HUB_OFFLINE='1')
    import torch
    import numpy as np
    from diffusers import RFD4ProteinaPipeline
    if not torch.backends.mps.is_available(): raise RuntimeError('RFD4 requires Apple MPS.')
    torch.set_num_threads(4)
    model = root / 'models/rfd4/diffusers'
    pipe = RFD4ProteinaPipeline.from_pretrained(str(model), dtype=torch.bfloat16, local_files_only=True).to('mps')
    pipe.transformer.eval().requires_grad_(False)
    pipe.vae.eval().requires_grad_(False)
    cfg = config['settings']
    records = []
    with torch.inference_mode():
        for index in range(1 if first_only else cfg['count']):
            seed = cfg['seed'] + index
            if cfg['optimized_kernels'] and index == 0:
                control = call(pipe, config, seed, output / 'qualification/reference', False)
            result = call(pipe, config, seed, output / 'generation' / f'seed_{seed}', cfg['optimized_kernels'])
            if cfg['optimized_kernels'] and index == 0:
                with np.load(control['tensors']) as a, np.load(result['tensors']) as b:
                    parity = set(a.files) == set(b.files) and all(np.array_equal(a[k], b[k]) for k in a.files)
                if not parity: raise ValueError('Optimized RFD4 differs from the reference on this input; campaign stopped.')
                seal(output / 'qualification/completed.json', dict(passed=True, seed=seed),
                     [output / 'qualification/reference/completed.json', output / 'generation' / f'seed_{seed}' / 'completed.json'])
            records.append(result)
            atomic(output / 'progress.json', dict(stage='generation', completed=index+1, total=cfg['count']))
            print('RFD4_GENERATED', index+1, cfg['count'], seed, flush=True)
    atomic(output / 'generated.json', records)
    if not first_only:
        seal(output / 'generation_completed.json', dict(count=len(records)),
             [output / 'generated.json'] + [output / 'generation' / r['id'] / 'completed.json' for r in records])


if __name__ == '__main__': main(sys.argv[1])
