"""Contract regression tests; learned inference is qualified separately via MCP."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import esmfold2_predict as adapter
from engine_adapters import command_for
from engine_registry import descriptor

class ESMFold2ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'job.yaml'
        self.input.write_text('sequences:\n- protein: {id: A, sequence: ACDEFGHIK, msa: empty}\nversion: 1\n')

    def test_fast_refuses_imported_msa_but_explicit_check_records_sequence_only(self):
        msa = self.root / 'target.a3m'; msa.write_text('>q\nACDEFGHIK\n>h\nACDEFGHIK\n')
        self.input.write_text(self.input.read_text().replace('msa: empty', 'msa: target.a3m'))
        with self.assertRaisesRegex(ValueError, 'sequence-only'): adapter.read_input(self.input, 'fast')
        chains, files = adapter.read_input(self.input, 'fast', True)
        self.assertEqual(chains[0]['msa'], 'empty'); self.assertEqual(files, {})
        chains, files = adapter.read_input(self.input, 'full')
        self.assertEqual(list(files.values()), [adapter.sha(msa)])
        msa.write_text('>q\nACDEFGHIA\n>h\nACDEFGHIA\n')
        with self.assertRaisesRegex(ValueError, 'does not match'): adapter.read_input(self.input, 'full')

    def test_rejects_unknown_constraints_and_x_tokens_before_model_load(self):
        self.input.write_text(self.input.read_text() + 'constraints: [{pocket: {binder: A}}]\n')
        with self.assertRaisesRegex(ValueError, 'restraints'): adapter.read_input(self.input, 'full')
        self.input.write_text(self.input.read_text().replace('ACDEFGHIK', 'ACDEXGHIK'))
        with self.assertRaisesRegex(ValueError, 'X-token'): adapter.read_input(self.input, 'full', True)

    def test_never_claims_affinity_or_hallucination_in_registry(self):
        for model in ('fast', 'full'):
            engine = 'esmfold2-' + model + '-mlx'
            d = descriptor(engine)
            self.assertEqual(d['capabilities'], ['structure'])
            cmd, env = command_for(engine, self.input, self.root/'out', self.root, 'v2-flash', self.root)
            self.assertIn('--unrestrained-check', cmd)
            self.assertIn(model, cmd)
            self.assertEqual(env['HF_HUB_OFFLINE'], '1')
            self.assertEqual(d['mappings']['venvs/NanoHunter_esmfold2'], 'python')

    def test_committed_receipt_rejects_tampering_and_changed_settings(self):
        directory = self.root / 'output'; directory.mkdir()
        f = directory/'model.cif'; f.write_text('saved prediction')
        identity = {'seed':42}
        adapter.atomic(directory/'complete.json', dict(identity=identity, files={'model.cif':adapter.sha(f)}))
        self.assertTrue(adapter.complete(directory, identity))
        self.assertFalse(adapter.complete(directory, {'seed':43}))
        f.write_text('tampered prediction')
        self.assertFalse(adapter.complete(directory, identity))

    def test_nise_final_shortlist_deduplicates_and_excludes_intermediates(self):
        sys.path.insert(0, str(SCRIPTS/'nise'))
        from final_checks import shortlist
        folder=self.root/'candidates';folder.mkdir()
        for i, (seq,score,branch,passed) in enumerate([('ACDEFG',1.9,'mpnn',True),('ACDEFG',1.8,'mpnn',True),('ACDEFA',2.0,'masked-backbone',True),('ACDEFP',1.7,'mpnn',False),('ACDEFW',1.6,'mpnn',True)]):
            (folder/f'{i}.json').write_text(json.dumps(dict(name=str(i),sequence=seq,score=score,branch=branch,passed=passed,trajectory=0)))
        self.assertEqual([r['name'] for r in shortlist(self.root,2)],['0','4'])


class ESMFold2NISETests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SCRIPTS/'nise'))

    def test_esmf_requires_sequence_objective_and_rejects_pool_or_noising(self):
        from contract import normalize
        base=dict(smiles='CCC', folding_engine='esmfold2-fast-mlx')
        with self.assertRaisesRegex(ValueError, 'requires'): normalize(base)
        base.update(scoring_mode='screening',nesso_screen=True,phase0_nesso_screen=True)
        for engine in ('nesso','psichic'):
            cfg=normalize(dict(base,screening_engine=engine))
            self.assertEqual(cfg['folding_engine'],'esmfold2-fast-mlx')
            self.assertTrue(cfg['selective_affinity'])
        with self.assertRaisesRegex(ValueError,'pool'): normalize(dict(base,resident_workers=2,scheduler='resident'))
        with self.assertRaisesRegex(ValueError,'Partial noising'): normalize(dict(base,partial_noising=True))
        self.assertEqual(normalize(dict(smiles='CCC'))['folding_engine'],'boltz')

    def test_atom_conversion_follows_input_order_and_rejects_missing_atom(self):
        import gemmi
        from esmfold_runtime import convert_structure
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'pred_min').mkdir()
            structure=gemmi.Structure();model=gemmi.Model('1');chain=gemmi.Chain('B');residue=gemmi.Residue()
            residue.name='LIG';residue.seqid=gemmi.SeqId(1,' ');residue.het_flag='H'
            for name,el,x in [('C2','C',0),('O1','O',1.4)]:
                atom=gemmi.Atom();atom.name=name;atom.element=gemmi.Element(el);atom.pos=gemmi.Position(x,0,0);residue.add_atom(atom)
            chain.add_residue(residue);model.add_chain(chain);structure.add_model(model)
            structure.make_mmcif_document().write_file(str(root/'pred_min/model_0.cif'))
            mapping=dict(smiles='CO',atoms=[dict(index=0,name='C2',el='C'),dict(index=1,name='O1',el='O')])
            (root/'ligand_atom_map.json').write_text(json.dumps({'B':mapping}))
            manifest=dict(smiles_used='CO',atoms=[dict(index=0,name='C9',el='C'),dict(index=1,name='O8',el='O')])
            convert_structure(root,root/'converted.pdb',manifest)
            self.assertEqual([a.name for r in gemmi.read_structure(str(root/'converted.pdb'))[0]['B'] for a in r],['C9','O8'])
            mapping['atoms'][1]['name']='O99';(root/'ligand_atom_map.json').write_text(json.dumps({'B':mapping}))
            with self.assertRaisesRegex(ValueError,'names differ'): convert_structure(root,root/'bad.pdb',manifest)
            manifest['smiles_used']='OC'
            with self.assertRaisesRegex(ValueError,'chemical state'): convert_structure(root,root/'bad.pdb',manifest)


class AtomicHandoffTests(unittest.TestCase):
    def test_preserves_outer_workflow_request_when_committing(self):
        class FixtureSession:
            def predict(self, chains, seed, samples, directory, job):
                cif=directory/'result.cif';cif.write_text('data_fixture\n')
                conf=directory/'confidence_result.json';conf.write_text('{"confidence_score":0.8}')
                return [(cif,conf)]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'query.yaml';source.write_text('version: 1\nsequences:\n- protein: {id: A, sequence: ACDEFG, msa: empty}\n')
            dest=root/'out/query';dest.mkdir(parents=True)
            marker=dest/'studio_prediction_request.json';marker.write_text('{"request":"outer"}')
            with patch('live_structure_events.publish'),patch('live_structure_events.invalidate'),patch.object(adapter,'ligand_atom_maps',return_value={}):
                adapter.run(root,'fast',[source],root/'out',[42],1,session=FixtureSession())
            self.assertEqual(json.loads(marker.read_text()),{'request':'outer'})
            record=json.loads((dest/'complete.json').read_text())
            self.assertTrue(adapter.complete(dest,record['identity']))
            self.assertIn('studio_prediction_request.json',record['files'])

if __name__ == '__main__': unittest.main()
