"""The existing resident predictor and MPNN adapters behind general search."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from .contract import atomic, fixed, seal, sha, verify, residue_letter


def sequences(path):
    # Called by the ligand oracle before the protein Engine is initialized.
    if os.environ.get('NANOHUNTER_ROOT'):
        sys.path.insert(0, str(Path(os.environ['NANOHUNTER_ROOT']) / 'rfd3_scripts'))
    from protein_structure import read_protein_atoms
    atoms = read_protein_atoms(path)
    if not atoms or any(not math.isfinite(v) for a in atoms for v in (a.x, a.y, a.z)):
        raise ValueError('Parent structure has missing or nonfinite protein coordinates.')
    result = {}
    for atom in atoms:
        if atom.atom == 'CA': result[atom.chain] = result.get(atom.chain, '') + residue_letter(atom.residue)
    if any(set(value) - set('ACDEFGHIKLMNPQRSTVWY') for value in result.values()):
        raise ValueError('Search requires complete standard amino-acid sequences.')
    return result


def canonical_protein(path, config, destination):
    """Keep native CIF provenance and explicitly map the two protein roles.

    RFD4 preserves source chain IDs: a target A can leave the generated binder
    on B. Resolve a frozen target by sequence, never by coincidental length.
    """
    from protein_structure import write_selected_pdb
    observed = sequences(path)
    cfg = config['settings']
    from .targets import target_sequences
    targets = target_sequences(config)
    if not targets:
        targets = {cfg['target_chain']: observed.get(cfg['target_chain'])}
    if len(observed) != len(targets) + 1:
        raise ValueError('Generated structure does not contain every target chain and one binder.')
    mapping = {}
    for output_chain, sequence in targets.items():
        native_chain = config.get('target_native_chains', {}).get(output_chain)
        matches = [c for c, seq in observed.items() if seq == sequence and c not in mapping]
        if native_chain in matches:
            source = native_chain
        elif len(matches) == 1:
            source = matches[0]
        else:
            raise ValueError('Cannot identify the frozen target chain uniquely in the generated structure.')
        mapping[source] = output_chain
    binders = set(observed) - set(mapping)
    if len(binders) != 1: raise ValueError('Cannot identify the designed chain.')
    mapping[binders.pop()] = cfg['binder_chain']
    write_selected_pdb(path, destination, mapping)
    if sequences(destination) != {mapping[k]:v for k, v in observed.items()}:
        raise ValueError('Role normalization changed a protein sequence.')
    return destination


class Engine:
    def __init__(self, config):
        self.config = config
        self.cfg = config['settings']
        self.root = Path(os.environ['NANOHUNTER_ROOT'])
        self.scripts = Path(__file__).resolve().parents[1]
        self.output = Path(config['output'])
        self.worker = self.output / 'workers' / f'mpnn_{os.getpid()}'
        self.session = None
        for path in (self.root / 'rfd3_scripts', self.root / 'rfd3_overlay/scripts'):
            sys.path.insert(0, str(path))

    def evaluate(self, proposal, parent, unit, native=False):
        import yaml
        from protein_structure import write_selected_pdb
        unit = Path(unit)
        cfg = self.cfg
        binder = cfg['binder_chain']
        original = sequences(parent['structure'])
        from .targets import target_sequences
        targets = target_sequences(self.config) or {cfg['target_chain']: original.get(cfg['target_chain'])}
        if set(original) != {binder, *targets} or any(original[c] != seq for c, seq in targets.items()):
            raise ValueError('The parent target chains differ from the frozen target assembly.')
        sequence_done = unit / 'sequence_completed.json'
        if sequence_done.exists():
            saved = verify(sequence_done)
            if saved['parent_sha256'] != parent['structure_sha256']: raise ValueError('Saved sequence has a different parent.')
            sequence = saved['sequence']
        else:
            attempt = unit / ('sequence_attempt_' + str(time.time_ns()))
            attempt.mkdir(parents=True)
            pdb = attempt / 'parent.pdb'
            mapping = {binder: 'A', **{c: chr(66+i) for i, c in enumerate(targets)}}
            write_selected_pdb(parent['structure'], pdb, mapping)
            if sequences(pdb) != {mapping[c]: seq for c, seq in original.items()}:
                raise ValueError('Parent conversion changed sequence or chain identity.')
            if native:
                sequence = original[binder]
            else:
                repo = self.root / 'src/LigandMPNN'
                model, checkpoint = {
                    'solublempnn': ('soluble_mpnn', 'solublempnn_v_48_020.pt'),
                    'proteinmpnn': ('protein_mpnn', 'proteinmpnn_v_48_020.pt'),
                    'abmpnn': ('protein_mpnn', 'abmpnn.pt'),
                }[cfg['sequence_model']]
                command = [str(self.root / 'venvs/NanoHunter_ligandmpnn/bin/python'),
                           str(self.scripts / 'mpnn_worker.py'), 'submit', str(self.worker), str(os.getpid()),
                           str(repo / 'run.py'), '--pdb_path', str(pdb), '--out_folder', str(attempt),
                           '--model_type', model, '--checkpoint_' + model, str(repo / 'model_params' / checkpoint),
                           '--chains_to_design', 'A', '--temperature', str(cfg['temperature']),
                           '--seed', str(proposal['sequence_seed'])]
                if cfg['omit_amino_acids']: command += ['--omit_AA', cfg['omit_amino_acids']]
                if cfg['task'] == 'nanobody':
                    from nanobody_cdrs import parse_explicit, resolve_cdrs
                    ranges = resolve_cdrs(original[binder], explicit=parse_explicit(cfg['cdr_ranges']))['ranges']
                    mutable = {i for a, b in ranges.values() for i in range(a, b+1)}
                    command += ['--redesigned_residues', ' '.join('A' + str(i) for i in sorted(mutable))]
                with (attempt / 'mpnn.log').open('w') as log:
                    subprocess.run(command, cwd=repo, env=dict(os.environ, KMP_USE_SHM='0', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'),
                                   check=True, stdout=log, stderr=subprocess.STDOUT)
                from run_mpnn import parse_fasta
                files = list((attempt / 'seqs').glob('*.fa'))
                if len(files) != 1: raise ValueError('Sequence designer output cardinality mismatch.')
                records = parse_fasta(files[0])
                if len(records) != 1: raise ValueError('Expected one sequence per search proposal.')
                sequence = records[0][0]
                if cfg['task'] == 'nanobody' and any(a != b for i, (a, b) in enumerate(zip(sequence, original[binder]), 1) if i not in mutable):
                    raise ValueError('Sequence design changed the nanobody framework.')
            if len(sequence) != len(original[binder]) or set(sequence) - set('ACDEFGHIKLMNPQRSTVWY'):
                raise ValueError('Designed sequence length or alphabet differs from the requested binder.')
            atomic(attempt / 'sequence.json', dict(sequence=sequence, parent_sha256=parent['structure_sha256']))
            seal(sequence_done, dict(sequence=sequence, parent_sha256=parent['structure_sha256']),
                 [pdb, attempt / 'sequence.json'] + list((attempt / 'seqs').glob('*.fa')))
        inputs = unit / 'inputs'
        inputs.mkdir(exist_ok=True)
        msa = 'empty'
        if cfg['task'] == 'nanobody' and cfg['scaffold_msa'] != 'empty' and cfg['predictor'] not in {'esmfold2-fast-mlx', 'esmfold2-600-mlx'}:
            msa = str(inputs / 'scaffold.a3m')
            subprocess.run([sys.executable, str(self.scripts / 'nanobody_masked_msa.py'), cfg['scaffold_msa'], msa,
                            sequence, original[binder], 'CDR1 CDR2 CDR3', cfg['cdr_ranges'],
                            str(self.scripts.parent / 'examples/nanobody_scaffolds/catalog.tsv'), '128', '-'], check=True)
        target_msa = 'empty' if cfg['predictor'] in {'esmfold2-fast-mlx', 'esmfold2-600-mlx'} else cfg['target_msa']
        document = dict(version=1, sequences=[dict(protein=dict(id=binder, sequence=sequence, msa=msa)),
                                             *[dict(protein=dict(id=c, sequence=seq, msa=self.config.get('target_msas', {}).get(c, target_msa))) for c, seq in targets.items()]])
        yp = inputs / (proposal['id'] + '.yaml')
        text = yaml.safe_dump(document, sort_keys=False)
        if yp.exists() and yp.read_text() != text: raise ValueError('Saved prediction input changed.')
        yp.write_text(text)
        predictions = unit / 'predictions'
        started = time.perf_counter()
        if cfg['predictor'].startswith('esmfold2-'):
            from esmfold2_predict import run
            profile = {'esmfold2-full-mlx': 'full', 'esmfold2-fast-mlx': 'fast', 'esmfold2-600-mlx': '600'}[cfg['predictor']]
            self.session = run(self.root, profile, [yp], predictions, [proposal['predictor_seed']], 1, session=self.session)
            leaf = predictions / yp.stem
            structure = leaf / 'pred_min/model_0.cif'
            confidence = leaf / 'pred_min/confidence.json'
            receipt = leaf / 'complete.json'
            verify(receipt)
            artifacts = [receipt]
        else:
            from resident_predictor import BoltzSession
            if self.session is None:
                self.session = BoltzSession(dict(root=str(self.root), model='boltz2', engine_args=['--seed', '42', '--diffusion_samples', '1']))
            self.session.predict(inputs, predictions, 1)
            confidences = list(predictions.rglob('confidence_*_model_0.json'))
            structures = list(predictions.rglob('*_model_0.cif')) + list(predictions.rglob('*_model_0.pdb'))
            if len(confidences) != 1 or len(structures) != 1: raise ValueError('Boltz output cardinality mismatch.')
            structure, confidence = structures[0], confidences[0]
            artifacts = [p for p in predictions.rglob('*') if p.is_file()]
        observed = sequences(structure)
        if observed != {binder: sequence, **targets}:
            raise ValueError('Predicted chain sequences differ from the supplied candidate.')
        scores = json.loads(confidence.read_text())
        if 'ipsae_min' not in scores:
            import numpy as np
            from ipsae_score import calculate_ipsae
            pae_files = list(predictions.rglob('pae_*_model_0.npz'))
            if len(pae_files) != 1: raise ValueError('Protein search requires an audited PAE matrix.')
            with np.load(pae_files[0], allow_pickle=False) as values: pae = values['pae']
            chain_map = [binder] * len(sequence) + [c for c, seq in targets.items() for _ in seq]
            if pae.shape != (len(chain_map), len(chain_map)): raise ValueError('PAE shape does not match the protein chains.')
            scores.update(calculate_ipsae(pae, chain_map, [binder, *targets]))
        score = float(scores['ipsae_min'])
        if not math.isfinite(score): raise ValueError('Nonfinite interface score.')
        record = dict(sequence=sequence, sequences=observed, structure=str(structure), structure_sha256=sha(structure),
                      confidence=str(confidence), score=score, ipsae_min=score, engine=cfg['predictor'],
                      target_chains=list(targets), score_scope='minimum_directional_ipSAE_across_all_protein_pairs',
                      score_role='native_feedback' if self.cfg['search'] != 'native' else 'native_sequence_assessment',
                      prediction_and_audit_seconds=time.perf_counter()-started)
        return record, [sequence_done, yp, *artifacts] + ([Path(msa)] if msa != 'empty' else [])

    def close(self):
        if self.session is not None and hasattr(self.session, 'close'): self.session.close()
        ready = self.worker / 'ready.json'
        if ready.exists():
            (Path(json.loads(ready.read_text())['session']) / 'STOP').touch()
