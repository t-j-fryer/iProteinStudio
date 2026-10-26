"""Bounded Boltz beta cycling using the existing resident predictor worker.

Model outputs stay immutable. A completed operation is reused only after its
input and output hashes match. This module is invoked only by the managed pilot.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from .contract import atomic, digest, PROFILE
from .designers import prepare as prepare_designers, validate_sequence, chemistry_audit
from .geometry import evaluate, read
from .templates import prepare as prepare_template
from .search import advance, allocation, rank


def replay(marker, spec):
    if not marker.exists(): return None
    old = json.loads(marker.read_text())
    if old['input'] != spec or any(digest(marker.parent / p) != h for p, h in old['files'].items()):
        raise ValueError('Completed beta operation changed: ' + str(marker))
    return old['result']


def commit(marker, spec, result, files):
    atomic(marker, dict(input=spec, result=result,
                       files={str(Path(p).relative_to(marker.parent)): digest(p) for p in files}))
    return result


def fasta(path):
    records = []
    for block in path.read_text().split('>'):
        if block.strip(): records.append(''.join(block.splitlines()[1:]).strip())
    return records


def design(root, reference, structure, directory, designer, count, seed):
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / 'complete.json'
    spec = dict(reference=digest(reference), structure=digest(structure), designer=designer, count=count, seed=seed)
    saved = replay(marker, spec)
    if saved is not None: return saved
    prepared = prepare_designers(reference, structure, root / 'models/boltz2/mols', directory / 'inputs')
    dest = directory / 'native'; dest.mkdir(exist_ok=True)
    if designer == 'ligandmpnn':
        repo = root / 'src/LigandMPNN'
        command = [root / 'venvs/NanoHunter_ligandmpnn/bin/python', repo / 'run.py',
                   '--model_type', 'ligand_mpnn', '--checkpoint_ligand_mpnn', repo / 'model_params/ligandmpnn_v_32_010_25.pt',
                   '--pdb_path', directory / 'inputs/ligandmpnn.pdb', '--out_folder', dest,
                   '--temperature', '0.5', '--seed', str(seed), '--number_of_batches', str(count),
                   '--ligand_mpnn_use_side_chain_context', '1', *prepared['ligandmpnn_args']]
    else:
        repo = root / 'src/LASErMPNN'
        command = [root / 'venvs/NanoHunter_lasermpnn/bin/python', root / 'scripts/run_lasermpnn_seeded.py', str(seed),
                   directory / 'inputs/lasermpnn.pdb', dest, str(count), '--device', 'cpu',
                   '--model_weights_path', repo / 'model_weights/laser_weights_0p1A_nothing_heldout.pt',
                   '--sequence_temp', '0.5', '--first_shell_sequence_temp', '0.7',
                   '--disabled_residues', 'X', '--output_fasta_only', '--silent', *prepared['lasermpnn_args']]
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', KMP_USE_SHM='0')
    with (directory / 'sampling.log').open('a') as log:
        subprocess.run([str(v) for v in command], cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    paths = sorted((dest / 'seqs').glob('*.fa')) if designer == 'ligandmpnn' else [dest / 'designs.fasta']
    sequences = []
    for path in paths:
        records = fasta(path)
        sequences += records[1:] if designer == 'ligandmpnn' else records
    if len(sequences) != count:
        raise ValueError(f'{designer} returned {len(sequences)} sequences, expected {count}.')
    # Never repair a mutation by overwriting the returned sequence.
    result = []
    for sequence in sequences:
        try:
            validate_sequence(reference, sequence)
            result.append(dict(sequence=sequence, valid=True))
        except ValueError as exc:
            result.append(dict(sequence=sequence, valid=False, error=str(exc)))
    return commit(marker, spec, result, paths + list((directory / 'inputs').glob('*')))


class Predictor:
    """One existing resident Boltz worker; immutable directory requests."""
    def __init__(self, root, output, seed):
        self.root, self.output, self.seed = root, output, seed
        self.process = None

    def start(self):
        if self.process is not None: return
        self.queue = self.output / 'sessions' / uuid.uuid4().hex
        self.queue.mkdir(parents=True)
        config = self.queue / 'config.json'
        atomic(config, dict(root=str(self.root), engine='boltz', model='boltz2', queue=str(self.queue),
               owner_pid=os.getpid(), use_potentials=False, allow_affinity=False, motif_sparse_templates=True,
               engine_args=['--accelerator', 'gpu', '--devices', '1', '--num_workers', '0',
                            '--output_format', 'pdb', '--preprocessing-threads', '1',
                            '--cache', str(self.root / 'models/boltz2'), '--seed', str(self.seed)]))
        self.stream = (self.queue / 'worker.log').open('w')
        self.process = subprocess.Popen([str(self.root / 'venvs/NanoHunter_boltz/bin/python'),
            str(self.root / 'scripts/resident_predictor.py'), '--config', str(config)],
            stdout=self.stream, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK='0'))
        try:
            ready = self.wait(self.queue / 'ready.json')
            if (ready['config_sha256'] != digest(config) or ready['pid'] != self.process.pid
                    or ready['model_load_count'] != 1 or ready['device'] != 'mps' or ready['fallback'] != 0):
                raise ValueError('Invalid resident predictor readiness receipt.')
        except BaseException:
            self.close(); raise

    def wait(self, path):
        deadline = time.monotonic() + 7200
        while not path.exists():
            if self.process.poll() is not None: raise RuntimeError('Predictor exited; see ' + str(self.queue / 'worker.log'))
            if time.monotonic() > deadline: raise RuntimeError('Predictor response timed out; see ' + str(self.queue / 'worker.log'))
            time.sleep(.2)
        return json.loads(path.read_text())

    def predict(self, documents, directory, seed):
        spec = dict(documents=documents, seed=seed)
        marker = directory / 'complete.json'
        saved = replay(marker, spec)
        if saved is not None: return saved
        inputs = directory / 'yaml'; inputs.mkdir(parents=True, exist_ok=True)
        for name, document in documents.items(): atomic(inputs / (name + '.yaml'), document)
        from resident_predictor import input_digest
        checksum, _ = input_digest(inputs)
        self.start()
        identifier = uuid.uuid4().hex; name = 'request_' + identifier + '.json'
        atomic(self.queue / 'requests' / name, dict(request_id=identifier, input_dir=str(inputs),
               output_dir=str(directory / 'out'), expected_jobs=len(documents), input_sha256=checksum,
               phase='structure', prediction_seed=seed))
        receipt = self.wait(self.queue / 'responses' / name)
        if (not receipt.get('ok') or receipt.get('request_id') != identifier
                or receipt.get('input_sha256') != checksum or receipt.get('completed_jobs') != len(documents)
                or receipt.get('model_load_count') != 1 or receipt.get('prediction_seed') != seed):
            raise ValueError('Prediction failed: ' + str(receipt))
        result, files = {}, []
        for name in documents:
            found = list((directory / 'out').rglob(name + '_model_0.pdb'))
            if len(found) != 1: raise ValueError('Missing/ambiguous prediction for ' + name)
            result[name] = str(found[0]); files.append(found[0])
        return commit(marker, spec, result, files + list(inputs.glob('*.yaml')))

    def close(self):
        if self.process is None: return
        if self.process.poll() is None:
            atomic(self.queue / 'stop.json', {})
            try: self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try: self.process.wait(timeout=10)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        self.stream.close(); self.process = None


def document(reference, sequence):
    ref = json.loads(Path(reference).read_text())
    return dict(version=1, sequences=[dict(protein=dict(id='A', sequence=sequence, msa='empty'))] +
                [dict(ligand=dict(id=l['key'].split(':')[0], ccd=l['component'])) for l in ref['ligands']])


def run(root, output, cfg, roots, *, predictor_factory=Predictor, designer=design):
    audit = chemistry_audit(json.loads((output / 'bundle/case.json').read_text()), root / 'models/boltz2/mols')
    atomic(output / 'chemistry.json', audit)
    if not audit['ready']: raise ValueError('Resolve the CCD/fixture chemistry mismatch before cycling: ' + str(audit['blockers']))
    predictor = predictor_factory(root, output, cfg['seed'])
    archive, failures, attempts = [], [], 0
    started = time.monotonic()
    try:
        for ri, root_record in enumerate(roots):
            reference = Path(root_record['reference'])
            initial = dict(id='root', structure=root_record['backbone'])
            for d in cfg['designers']:
                for policy in cfg['policies']:
                    arm = root_record['id'] + '/' + d + '-' + policy
                    parents, best = [initial], []
                    for cycle in range(cfg['cycles']):
                        print(f'MOTIFBETA|cycle|{arm} {cycle + 1}/{cfg["cycles"]}', flush=True)
                        directory = output / 'cycles' / arm / f'{cycle + 1:03d}'
                        if not parents:
                            atomic(directory / 'extinct.json', dict(reason='No fold-qualified parent passed the source geometry guard.'))
                            break
                        units = allocation(parents, cfg['proposals'])
                        if policy == 'iterative' and cycle > 0:
                            units = [(p, 1) for p in parents]
                        candidates, documents = [], {}
                        slot = 0
                        seed = 1 + (cfg['seed'] + ri * 100000 + cycle * 1000) % 2147480000
                        for pi, (parent, count) in enumerate(units):
                            proposals = designer(root, reference, Path(parent['structure']), directory / f'design_{pi:03d}', d, count, seed + pi)
                            for proposal in proposals:
                                name = f'candidate_{slot:04d}'; slot += 1; attempts += 1
                                identity = arm + '/' + str(cycle + 1) + '/' + name
                                if not proposal['valid']:
                                    failures.append(dict(id=identity, error=proposal['error'])); continue
                                candidate = dict(id=identity, name=name, sequence=proposal['sequence'], parent=parent['id'],
                                    trajectory=parent.get('trajectory', slot - 1), root=root_record['id'], arm=d + '-' + policy, cycle=cycle + 1)
                                candidates.append(candidate)
                                documents[name] = document(reference, proposal['sequence'])
                        if not candidates:
                            parents = []
                            continue
                        guided = {}
                        if cfg['guidance']:
                            guide_docs = {}
                            for candidate in candidates:
                                name = candidate['name']
                                guide_reference = reference
                                if cfg.get('guidance_source', 'rfd3-root') == 'benchmark-residues':
                                    from .source_guide import prepare as prepare_source
                                    root_ref = json.loads(reference.read_text())
                                    guide_reference = directory / 'templates' / name / 'source-guide.json'
                                    prepare_source(cfg['case_id'], root_ref['source_to_query'], candidate['sequence'], guide_reference)
                                template = prepare_template(guide_reference, candidate['sequence'], 'boltz', directory / 'templates' / name)
                                guide_docs[name] = {**documents[name], **template['fragment']}
                            guided = predictor.predict(guide_docs, directory / 'guided', seed)
                        checked = predictor.predict(documents, directory / 'untemplated', seed)
                        eligible = []
                        for candidate in candidates:
                            name = candidate['name']; path = Path(checked[name])
                            try:
                                atoms = read(path)
                                confidence = [v['atoms']['CA']['b'] for k, v in atoms.items() if k.startswith('A:')]
                                metrics = evaluate(reference, path, sum(confidence) / len(confidence))
                                if metrics['sequence'] != candidate['sequence']:
                                    raise ValueError('Prediction sequence differs from submitted sequence.')
                                candidate.update(metrics=metrics, structure=guided.get(name, str(path)), checked_structure=str(path))
                                atomic(directory / (name + '.json'), candidate)
                                archive.append(candidate); eligible.append(candidate)
                            except ValueError as exc:
                                failures.append(dict(id=candidate['id'], error=str(exc)))
                        parents = ([initial] if policy == 'fixed' else
                                   advance(policy, eligible, cfg['beam_width'], previous=best if policy in ('greedy', 'beam') else ()))
                        best = rank(eligible, cfg['beam_width'], previous=best)
                        atomic(directory / 'selection.json', dict(parents=[p['id'] for p in parents], best=[p['id'] for p in best]))
        result = dict(profile=PROFILE, attempted_sequences=attempts, checked=len(archive),
            passed=sum(r['metrics']['guarded_pass'] for r in archive), failures=failures,
            candidates=archive, wall_seconds_this_invocation=time.monotonic() - started,
            scheduler='one resident Boltz worker; sequential CPU inverse folding; directory requests per arm/cycle',
            independent_family_validation=False, experimental_validation=False,
            interpretation='Beta search results, not independently validated enzyme hits; duplicate sequences retained in denominators.')
        atomic(output / 'comparison_results.json', result)
        return result
    finally:
        predictor.close()
