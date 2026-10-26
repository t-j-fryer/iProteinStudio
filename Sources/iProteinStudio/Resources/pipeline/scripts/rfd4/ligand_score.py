"""Native-rollout oracle using the existing NISE Boltz worker and receipts."""
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from .contract import sha


class Engine:
    def __init__(self, config):
        self.config = config
        self.output = Path(config['output'])
        self.scripts = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(self.scripts / 'nise'))
        import batch_runtime
        class Client(batch_runtime.BatchClient):
            worker_script = str(Path(__file__).with_name('native_boltz_worker.py'))
        batch_runtime.BatchClient = Client
        settings = dict(scheduler='resident', scoring_mode='boltz', nesso_screen=False,
                        folding_engine='boltz', smiles=config['settings']['ligand_smiles'])
        # Same two-resident-worker policy used in the completed native search.
        self.backend = batch_runtime.PoolBackend(os.environ['NANOHUNTER_ROOT'], self.output,
                                                 settings, self.scripts, workers=2)

    def score(self, key, structures):
        from rfd4.search_engine import sequences
        seqs = {}
        for name, path in structures.items():
            chains = sequences(path)
            if len(chains) != 1: raise ValueError('Native ligand scoring requires exactly one protein chain.')
            seqs[name] = next(iter(chains.values()))
        return self.score_sequences(key, seqs)

    def score_sequences(self, key, seqs):
        from runtime import Backend
        directory = self.output / 'native_predictions' / key
        args = SimpleNamespace(seed=42, use_potentials=True, boltz_phase='structure', skip_nesso=True,
                               prediction_seeds={name:42 for name in seqs})
        predictions = self.backend.fold(seqs, self.config['settings']['ligand_smiles'], directory, args, pocket=None)
        predictions = self.backend.affinity(predictions, directory, args)
        rows = {}
        for name, prediction in predictions.items():
            Backend.audit_structure(prediction.pdb, seqs[name], True)
            pbind, confidence = prediction.pbind, prediction.ligand_plddt
            if not all(type(v) in (int, float) and math.isfinite(v) for v in (pbind, confidence)) or not 0 <= pbind <= 1 or not 0 <= confidence <= 100:
                raise ValueError('Native Boltz oracle returned an invalid probability or confidence.')
            rows[name] = dict(sequence=seqs[name], score=pbind+confidence/100,
                metrics={'boltz.pbind':pbind, 'boltz.ligand_plddt':confidence},
                structure=prediction.pdb, structure_sha256=sha(prediction.pdb),
                receipts=[str(directory / name / f) for f in ('completed.json', 'affinity_completed.json')])
        if set(rows) != set(seqs): raise ValueError('Native oracle omitted a rollout.')
        return rows

    def close(self):
        self.backend.close_design()
        self.backend.close()
