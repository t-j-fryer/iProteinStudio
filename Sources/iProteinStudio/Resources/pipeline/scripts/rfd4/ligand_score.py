"""Native-rollout oracle using the existing NISE Boltz worker and receipts."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from .contract import sha, selection_score, selection_metric


def esm_ligand_manifest(smiles):
    """Use the selected predictor's native atom identity, without Boltz chemistry.

    RFD4 confidence-only scoring receives the generation molecule unchanged.
    NISE's Boltz-standardized manifest is still supplied by its own campaign.
    """
    from esmfold2_predict import ligand_atom_maps
    native = ligand_atom_maps([dict(kind='ligand', id='B', smiles=smiles)])['B']
    identity = dict(schema=1, smiles_used=native['smiles'], atoms=native['atoms'],
                    rdkit_version=native['rdkit_version'], naming='esmfold2-native-input-order')
    return dict(identity, signature=hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest())


class Engine:
    def __init__(self, config):
        self.config = config
        self.output = Path(config['output'])
        self.scripts = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(self.scripts / 'nise'))
        import batch_runtime
        self.predictor = config['settings']['predictor']
        class Client(batch_runtime.BatchClient):
            worker_script = str(Path(__file__).with_name('native_boltz_worker.py'))
        batch_runtime.BatchClient = Client
        settings = dict(scheduler='resident', scoring_mode='boltz', nesso_screen=False,
                        folding_engine='boltz', smiles=config['settings']['ligand_smiles'])
        # Same two-resident-worker policy used in the completed native search.
        if self.predictor == 'boltz':
            self.backend = batch_runtime.PoolBackend(os.environ['NANOHUNTER_ROOT'], self.output, settings, self.scripts, workers=2)
        else:
            from esmfold_runtime import ESMBackend
            # Reuse the qualified complete-sequence ligand prediction/atom-map
            # adapter. RFD4 owns the objective; no NISE screening is invoked.
            class ConfidenceBackend(ESMBackend):
                @property
                def allow_boltz_affinity(self): return False
            settings['folding_engine']=self.predictor
            self.backend=ConfidenceBackend(os.environ['NANOHUNTER_ROOT'],self.output,settings,self.scripts)
            self.backend.ligand_manifest = esm_ligand_manifest(settings['smiles'])

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
        if self.predictor == 'boltz': predictions = self.backend.affinity(predictions, directory, args)
        rows = {}
        for name, prediction in predictions.items():
            Backend.audit_structure(prediction.pdb, seqs[name], True)
            pbind, confidence = prediction.pbind, prediction.ligand_plddt
            if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0 <= confidence <= 100:
                raise ValueError('Ligand predictor returned invalid ligand pLDDT.')
            rows[name] = dict(sequence=seqs[name], score=selection_score(self.config['settings'], dict(pbind=pbind, ligand_plddt=confidence, iptm=getattr(prediction,'iptm',None), complex_plddt=getattr(prediction,'complex_plddt',None))),
                selection_metric=selection_metric(self.config['settings']),
                metrics={'boltz.pbind':pbind, 'boltz.ligand_plddt':confidence} if self.predictor=='boltz' else {'ligand_plddt':confidence},
                structure=prediction.pdb, structure_sha256=sha(prediction.pdb),
                receipts=[str(directory / name / f) for f in (('completed.json', 'affinity_completed.json') if self.predictor=='boltz' else ('completed.json',))])
        metric=selection_metric(self.config['settings'])
        if metric!='pbind_ligand_plddt':
            for row in rows.values(): row['metrics'][metric]=row['score']
        if set(rows) != set(seqs): raise ValueError('Native oracle omitted a rollout.')
        return rows

    def close(self):
        self.backend.close_design()
        self.backend.close()
