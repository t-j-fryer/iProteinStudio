"""ESMFold2 structures with NESSO/PSICHIC selection and unchanged NISE geometry.

Initial X-token backbones remain Boltz. Complete sequences use the selected
MLX model without pocket restraints, affinity or MSAs; this is an explicit
experimental route, never a fallback from Boltz.
"""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from types import SimpleNamespace
import uuid

from batch_runtime import BatchBackend
from runtime import ResidentClient, atomic, digest, input_digest


class ESMClient(ResidentClient):
    def __init__(self, root, output, scripts, engine, seed):
        self.queue = Path(output) / 'sessions' / ('esmfold2-' + uuid.uuid4().hex)
        self.queue.mkdir(parents=True)
        self.log = self.queue / 'worker.log'
        self.config = self.queue / 'config.json'
        atomic(self.config, dict(root=str(root), engine=engine, queue=str(self.queue),
            seed=str(seed), samples=1, owner_pid=os.getpid(), unrestrained_check=False))
        self.stream = self.log.open('w')
        self.process = subprocess.Popen([str(root / 'venvs/NanoHunter_esmfold2/bin/python'),
            '-B', str(scripts / 'resident_predictor.py'), '--config', str(self.config)],
            stdout=self.stream, stderr=subprocess.STDOUT, env=dict(os.environ,
                HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTORCH_ENABLE_MPS_FALLBACK='0'))
        try:
            self.ready = self.wait(self.queue / 'ready.json')
            if (self.ready.get('device') != 'mlx' or self.ready.get('fallback') != 0
                    or self.ready.get('pid') != self.process.pid or self.ready.get('model_load_count') != 1
                    or self.ready.get('config_sha256') != digest(self.config)):
                raise RuntimeError('Invalid ESMFold2 resident readiness receipt')
        except BaseException:
            self.close(); raise

    def submit(self, source, output, names, on_item):
        identifier = uuid.uuid4().hex
        filename = 'request_' + identifier + '.json'
        checksum = input_digest(source)
        atomic(self.queue / 'requests' / filename, dict(request_id=identifier,
            input_dir=str(source), output_dir=str(output), expected_jobs=len(names), input_sha256=checksum))
        response = self.queue / 'responses' / filename
        seen = set(); deadline = time.monotonic() + 1800
        while True:
            for name in names:
                if name not in seen and (output / name / 'complete.json').is_file():
                    on_item(name); seen.add(name); deadline = time.monotonic() + 1800
            if response.exists():
                receipt = json.loads(response.read_text())
                if (not receipt.get('ok') or receipt.get('request_id') != identifier
                        or receipt.get('input_sha256') != checksum or receipt.get('completed_jobs') != len(names)
                        or receipt.get('model_load_count') != 1):
                    raise RuntimeError(f'ESMFold2 request failed: {receipt}; see {self.log}')
                for name in names:
                    if name not in seen: on_item(name)
                return receipt
            if self.process.poll() is not None: raise RuntimeError(f'ESMFold2 worker exited; see {self.log}')
            if time.monotonic() > deadline: raise RuntimeError(f'No ESMFold2 completion for 30 minutes; see {self.log}')
            time.sleep(.1)


def convert_structure(native, destination, manifest=None):
    """Map atoms by identical SMILES input order, never by coordinate proximity."""
    import gemmi
    structure = gemmi.read_structure(str(native / 'pred_min/model_0.cif'))
    if manifest is not None:
        mapping = json.loads((native / 'ligand_atom_map.json').read_text())['B']
        if mapping['smiles'] != manifest['smiles_used']:
            raise ValueError('ESMFold2 ligand chemical state differs from the saved NISE molecule')
        source = {a['index']: a for a in mapping['atoms']}
        target = {a['index']: a for a in manifest['atoms']}
        if set(source) != set(target) or any(source[i]['el'] != target[i]['el'] for i in source):
            raise ValueError('ESMFold2 ligand atom identity mismatch')
        names = {source[i]['name']: target[i]['name'] for i in source}
        chain = structure[0].find_chain('B')
        if chain is None: raise ValueError('ESMFold2 omitted ligand chain B')
        atoms = [a for r in chain for a in r if not a.element.is_hydrogen]
        if len(atoms) != len(names) or {a.name for a in atoms} != set(names):
            raise ValueError('ESMFold2 output ligand names differ from its upstream atom map')
        for a in atoms: a.name = names[a.name]
    structure.write_pdb(str(destination))


class ESMBackend(BatchBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.esm_worker = None

    def close(self):
        if self.esm_worker is not None:
            self.esm_worker.close(); self.esm_worker = None
        super().close()

    def fold(self, sequences, smiles, directory, args, pocket=None, apo=False):
        directory = Path(directory)
        if any('X' in sequence for sequence in sequences.values()):
            if directory.name != 'cycle00' or apo:
                raise ValueError('ESMFold2 supports complete sequences only; X tokens are restricted to initial Boltz generation')
            try:
                return super().fold(sequences, smiles, directory, args, pocket, apo)
            finally:
                # Never retain the initialization model alongside ESMC-6B.
                if self.worker is not None: self.worker.close(); self.worker = None
        if self.allow_boltz_affinity:
            raise ValueError('ESMFold2 NISE requires NESSO or PSICHIC as the objective')
        if self.settings.get('nesso_screen') and not getattr(args, 'skip_nesso', False) and not apo and sequences and all(
                re.fullmatch(r'c\d+_t\d+_n\d+_s\d+', name) for name in sequences):
            from nesso_screen import screen
            sequences = screen(self, sequences, smiles, directory.parent / 'nesso',
                               allow_empty=self.settings.get('adaptive_proposals', False))
        from esmfold2_predict import complete, read_input, sha, PORT_REVISION, PROFILES
        from ligand_atoms import audit_atoms
        engine = self.settings['folding_engine']
        profile = 'fast' if engine == 'esmfold2-fast-mlx' else 'full'
        native_root = directory / '_esm_outputs'
        predictions, pending = {}, {}
        for name, sequence in sequences.items():
            unit = directory / name
            source = unit / 'yaml'; source.mkdir(parents=True, exist_ok=True)
            spec = dict(sequence=sequence, smiles=None if apo else smiles, seed=args.seed,
                folding_engine=engine, profile=list(PROFILES[profile]), port=PORT_REVISION,
                affinity=False, phase='structure', msa='empty', pocket_applied=False,
                upstream_pocket_request=pocket, potentials=False, atom_signature=None if apo else self.atom_manifest(smiles)['signature'])
            saved = self.journal.load(unit / 'completed.json', spec)
            if saved is not None:
                self.audit_structure(saved['prediction']['pdb'], sequence, not apo)
                if not apo: audit_atoms(saved['prediction']['pdb'], self.atom_manifest(smiles))
                predictions[name] = SimpleNamespace(**saved['prediction']); continue
            # JSON is also valid YAML; no design constraints enter this input.
            entries = [dict(protein=dict(id='A', sequence=sequence, msa='empty'))]
            if not apo: entries.append(dict(ligand=dict(id='B', smiles=smiles)))
            atomic(source / (name + '.yaml'), dict(version=1, sequences=entries))
            pending[name] = spec

        def commit(name):
            unit, native = directory / name, native_root / name
            path = unit / 'yaml' / (name + '.yaml')
            _, msas = read_input(path, profile)
            identity = dict(input_sha256=sha(path), msas=msas, model=profile, seeds=[args.seed], samples=1,
                profile=list(PROFILES[profile]), port=PORT_REVISION, unrestrained_check=False, schema=1)
            if not complete(native, identity): raise RuntimeError('Invalid ESMFold2 atomic output: ' + name)
            pdb = unit / (name + '.pdb')
            convert_structure(native, pdb, None if apo else self.atom_manifest(smiles))
            self.audit_structure(pdb, pending[name]['sequence'], not apo)
            if not apo: audit_atoms(pdb, self.atom_manifest(smiles))
            metrics = json.loads((native / 'pred_min/confidence.json').read_text())
            pred = self.science.Prediction(name=name, pdb=str(pdb), complex_plddt=metrics['complex_plddt'],
                iptm=metrics.get('iptm'), ligand_iptm=None, ligand_plddt=metrics.get('ligand_plddt'), pbind=None)
            files = [path, pdb] + [p for p in native.rglob('*') if p.is_file()]
            self.journal.save(unit / 'completed.json', pending[name], dict(prediction=asdict(pred),
                timing=dict(model_call_seconds=metrics['model_call_seconds']), folding_engine=engine), files)
            predictions[name] = pred
            atomic(self.output / 'progress.json', dict(message=f'Completed {name} with {engine}', scheduler=self.settings['scheduler']))
            print(f'NISE|completed|{name}|{engine}', flush=True)

        for name in list(pending):
            if (native_root / name / 'complete.json').is_file():
                commit(name); del pending[name]
        if pending:
            batch = directory / '_esm_requests' / uuid.uuid4().hex
            batch.mkdir(parents=True)
            for name in pending: shutil.copy2(directory / name / 'yaml' / (name + '.yaml'), batch / (name + '.yaml'))
            if self.esm_worker is None:
                self.esm_worker = ESMClient(self.root, self.output, self.scripts, engine, args.seed)
            self.esm_worker.submit(batch, native_root, list(pending), commit)
        if apo and self.settings['scheduler'] == 'cycle-wave': self.close()
        return {name: predictions[name] for name in sequences}
