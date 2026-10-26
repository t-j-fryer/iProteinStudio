"""Ligand proposals use the existing NISE sampler and verified Boltz oracle.

The family search controller retains fixed/iterative/greedy/beam semantics;
geometry is not silently substituted for the requested combined score.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from .contract import atomic, seal, sha, verify
from .ligand_score import Engine as Oracle
from .search_engine import sequences


class Engine:
    def __init__(self, config):
        self.config=config; self.cfg=config['settings']; self.oracle=Oracle(config)

    def evaluate(self, proposal, parent, unit, native=False):
        unit=Path(unit); cfg=self.cfg
        chains=sequences(parent['structure'])
        if len(chains)!=1: raise ValueError('Ligand search expects one protein chain and the declared molecule.')
        original=next(iter(chains.values()))
        marker=unit/'sequence_completed.json'
        if marker.exists():
            saved=verify(marker)
            if saved['parent_sha256']!=parent['structure_sha256']: raise ValueError('Changed ligand search parent.')
            sequence=saved['sequence']
        else:
            if native: sequence=original; files=[Path(parent['structure'])]
            else:
                if Path(parent['structure']).suffix.lower()!='.pdb': raise ValueError('Ligand sequence design needs an audited PDB parent.')
                args=SimpleNamespace(fs_distance=10.0,ala_budget=2,gly_budget=0)
                directory=unit/'sampling'
                values=self.oracle.backend.design(parent['structure'],directory,1,cfg['ligand_smiles'],args,
                    cfg['temperature'],0.7,proposal['sequence_seed'],'all',True)
                if len(values)!=1: raise ValueError('Expected one ligand sequence proposal.')
                sequence=values[0];files=[p for p in directory.rglob('*') if p.is_file()]
            if len(sequence)!=len(original) or set(sequence)-set('ACDEFGHIKLMNPQRSTVWY'):
                raise ValueError('Ligand sequence proposal changed length or has invalid residues.')
            seal(marker,dict(sequence=sequence,parent_sha256=parent['structure_sha256']),files)
        scored=self.oracle.score_sequences(proposal['id'],{proposal['id']:sequence})[proposal['id']]
        for receipt in scored['receipts']: verify(receipt,relative_root=self.config['output'])
        record=dict(sequence=sequence,sequences={'A':sequence},structure=scored['structure'],
            structure_sha256=scored['structure_sha256'],score=scored['score'],metrics=scored['metrics'],
            score_role='native_sequence_assessment' if native else 'sequence_search_feedback',engine='Boltz-2',
            oracle_receipts=scored['receipts'])
        return record,[marker,*scored['receipts']]

    def close(self): self.oracle.close()
