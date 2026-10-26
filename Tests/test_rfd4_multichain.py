"""Target identity, per-chain MSA policy and multichain authoring contracts."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
PIPE = REPO / 'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0] = [str(PIPE/'scripts'), str(REPO/'Sources/iProteinStudio/Resources/rfd3')]
from rfd4.contract import normalize
from rfd4.search_engine import canonical_protein, sequences
from rfd4.targets import hotspot_map, selected_chains
from rfd4.msas import resolve


def pdb(path, chains):
    lines=[]
    names={'A':'ALA','G':'GLY','S':'SER'}
    for chain, sequence in chains.items():
        for n, aa in enumerate(sequence, 1):
            lines.append(f'ATOM  {len(lines)+1:5d}  CA  {names[aa]} {chain}{n:4d}    {n*3.8:8.3f}{0.:8.3f}{0.:8.3f}  1.00 80.00           C  ')
    path.write_text('\n'.join(lines)+'\nEND\n')


class TargetTests(unittest.TestCase):
    def test_selection_hotspots_and_ambiguous_numbers(self):
        self.assertEqual(selected_chains(['C','B','C'], ''), ['C','B'])
        self.assertEqual(selected_chains(['B','C'], 'B,C'), ['B','C'])
        cfg=normalize(dict(task='protein',source='target.cif',hotspot_residues=['B32','C:55']))
        self.assertEqual(hotspot_map(cfg,['B','C']), {'B':[32], 'C':[55]})
        for changes in [dict(hotspots=[32]),dict(hotspot_residues=['D1']),dict(hotspot_residues=['B0']),dict(hotspot_residues=['B32','B:32'])]:
            with self.assertRaises(ValueError):hotspot_map(cfg|changes,['B','C'])

    def test_roles_preserve_homomers_and_reject_missing_or_mutated_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);source=root/'input.pdb';out=root/'roles.pdb'
            cfg=dict(settings=normalize(dict(task='protein',source=str(source))),
                     target_sequences={'B':'GGG','C':'GGG'},target_native_chains={'B':'B','C':'C'})
            pdb(source,{'A':'ASS','B':'GGG','C':'GGG'})
            canonical_protein(source,cfg,out)
            self.assertEqual(sequences(out),{'A':'ASS','B':'GGG','C':'GGG'})
            for changed in [{'A':'ASS','B':'GGG'}, {'A':'ASS','B':'GGG','C':'GGA'}]:
                pdb(source,changed)
                with self.assertRaises(ValueError):canonical_protein(source,cfg,out)
            pdb(source,{'A':'GGG','B':'ASS'})
            old=dict(settings=cfg['settings'],target_sequence='GGG')
            canonical_protein(source,old,out)
            self.assertEqual(sequences(out), {'B':'GGG','A':'ASS'})

    def test_shared_msa_resolution_per_chain_and_resume_hash_verification(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);out=root/'run';out.mkdir()
            def get(jobs, policy, runtime, env):
                self.assertEqual([c['id'] for c in jobs[0]['chains']], ['B','C','D'])
                self.assertTrue(policy['msa']['allow_server'])
                return {seq: root/(seq+'.a3m') for seq in ['GGG','ASS']}
            for seq in ['GGG','ASS']:(root/(seq+'.a3m')).write_text('>query\n'+seq+'\n')
            adapter=types.SimpleNamespace(resolve_msas=get,materialize_msas=lambda values,*args:values,sequence_key=lambda seq:seq)
            cfg=dict(settings=normalize(dict(task='protein',source='target.cif',target_msa='auto')),output=str(out),target_sequences={'B':'GGG','C':'ASS','D':'GGG'})
            with patch.dict(os.environ,NANOHUNTER_ROOT=str(root)),patch.dict(sys.modules,predict_batch=adapter):
                result=resolve(cfg)
                self.assertEqual(set(result['target_msas']), {'B','C','D'})
                self.assertEqual(result['target_msas']['B'],result['target_msas']['D'])
                self.assertEqual(resolve(cfg),result)
                (root/'GGG.a3m').write_text('changed')
                with self.assertRaises(ValueError):resolve(cfg)


if __name__=='__main__':unittest.main()
