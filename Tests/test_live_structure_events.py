"""Execute native-save adapters and read the receipts through the MCP consumer."""
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS.parent / 'mcp')]
import live_structure_events as live
from iprotein_mcp.live_results import records
from iprotein_mcp import catalog
PDB = 'ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 80.00           C  \nEND\n'

class LiveStructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, IPROTEINSTUDIO_LIVE_RESULTS_ROOT=str(self.root))
        self.env.start(); self.addCleanup(self.env.stop)

    def files(self, directory, structure, confidence):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / structure).write_text(PDB)
        if confidence: (directory / confidence).write_text('{"iptm": 0.8, "complex_plddt": 0.9}')

    def test_boltz_atomic_success_failure_stale_and_mcp_predict(self):
        test = self
        class Writer:
            output_dir = test.root / 'boltz/bucket_128/chunk_0/predictions'
            def write_on_batch_end(self, prediction, batch):
                test.assertEqual(records(test.root), [])
                name = batch['record'][0].id
                test.files(self.output_dir / name, name+'_model_0.pdb', 'confidence_'+name+'_model_0.json')
                if prediction.get('raise'): raise RuntimeError('native failure')
        module = SimpleNamespace(__name__='boltz.data.write.writer', BoltzWriter=Writer)
        live.instrument(module); live.instrument(module)
        writer = Writer(); batch={'record': [SimpleNamespace(id='input')]}
        writer.write_on_batch_end({}, batch)
        rows=records(self.root); self.assertEqual(len(rows),1); self.assertIsNone(rows[0]['is_hit'])
        with patch.object(catalog,'resolve_run',return_value=self.root), patch.object(catalog,'classify_run',return_value='prediction'):
            overview=catalog.results_overview('fixture')
            self.assertEqual(len(overview['groups'][0]['variants']),1)
            self.assertEqual(catalog.query_results('fixture','live_predictions',None,False,100)['rows'][0]['job'],'input')
        with self.assertRaisesRegex(RuntimeError,'native failure'): writer.write_on_batch_end({'raise':True},batch)
        self.assertEqual(records(self.root),[])
        writer.write_on_batch_end({},batch)
        (self.root/records(self.root)[0]['structure_path']).write_text('partial')
        self.assertEqual(records(self.root),[])

    def test_bootstrap_works_with_telemetry_disabled(self):
        from engine_progress import environment
        package = self.root / 'modules/runner'; package.mkdir(parents=True)
        (package / '__init__.py').write_text('')
        (package / 'dumper.py').write_text(
            'from pathlib import Path\nclass DataDumper:\n'
            ' def dump_predictions(self, pred_dict, dump_dir, pdb_id, atom_array, entity_poly_type, seed):\n'
            '  p=Path(dump_dir)/"predictions"; p.mkdir(parents=True)\n'
            '  (p/(pdb_id+"_sample_0.pdb")).write_text(' + repr(PDB) + ')\n'
            '  (p/(pdb_id+"_summary_confidence_sample_0.json")).write_text("{}")\n')
        env = environment({**os.environ, 'PYTHONPATH': str(package.parent), 'IPROTEINSTUDIO_PROGRESS': '0'}, SCRIPTS)
        code = 'from runner.dumper import DataDumper; DataDumper().dump_predictions({}, ' + repr(str(self.root/'protenix-v2/out')) + ', "input", None, {}, 1)'
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(records(self.root)), 1)
        self.assertNotIn('IPROTEINSTUDIO_PROGRESS|', result.stderr)

    def test_protenix_and_openfold_native_naming(self):
        test=self
        class Dumper:
            def dump_predictions(self, pred_dict, dump_dir, pdb_id, atom_array, entity_poly_type, seed):
                test.files(Path(dump_dir)/'predictions', pdb_id+'_sample_0.pdb',pdb_id+'_summary_confidence_sample_0.json')
        live.instrument(SimpleNamespace(__name__='runner.dumper',DataDumper=Dumper))
        Dumper().dump_predictions({},str(self.root/'protenix-mini/input/seed_1'),'input',None,{},1)
        self.assertEqual(records(self.root)[0]['predictor'],'protenix-mini')
        class Writer:
            output_dir=test.root/'openfold3'
            def write_all_outputs(self,batch,outputs,confidence_scores):
                test.files(self.output_dir/'other/seed_7','other_seed_7_sample_1_model.pdb','other_seed_7_sample_1_confidences_aggregated.json')
        live.instrument(SimpleNamespace(__name__='openfold3.core.runners.writer',OF3OutputWriter=Writer))
        Writer().write_all_outputs({'query_id':['other'],'seed':[7]}, {}, {})
        self.assertEqual({r['predictor'] for r in records(self.root)}, {'protenix-mini','openfold-3-mlx'})

    def test_intellifold_retains_all_seeds_and_cli_main(self):
        test=self
        def predict_and_save(args,model,input_features,record,structure,out_dir,seed):
            test.files(Path(out_dir)/'predictions'/record.id, f'{record.id}_seed-{seed}_sample-0.pdb',f'{record.id}_seed-{seed}_sample-0_summary_confidences.json')
            return 'unchanged'
        module=SimpleNamespace(predict_and_save=predict_and_save)
        live.instrument_intellifold(module)
        for seed in (1,2): self.assertEqual(module.predict_and_save(None,None,None,SimpleNamespace(id='input'),None,self.root/'intellifold',seed),'unchanged')
        self.assertEqual(len(records(self.root)),2)
        script=self.root/'fixture.py'
        script.write_text('def predict_and_save(args,model,input_features,record,structure,out_dir,seed):\n return 9\nif __name__ == "__main__":\n executed=True\n')
        namespace=live.run_intellifold(script)
        self.assertTrue(namespace['executed']); self.assertTrue(namespace['predict_and_save']._studio_live_writer)

    def test_rfd3_offsets_and_nise_pending_results(self):
        for offset in (0,6):
            directory=self.root/f'phase0/cycle00/rfd3/bin/queue{offset}'
            self.files(directory,'design_0001.pdb',None)
            with patch.dict(os.environ,IPROTEINSTUDIO_RFD3_LIVE_OFFSET=str(offset)):
                live.publish_backbone(directory/'design_0001.pdb',1)
        self.assertEqual({r['job'] for r in records(self.root)},{'design_0001','design_0007'})
        overview=catalog._nise_overview(self.root,100)
        variants=[v for g in overview['groups'] for v in g['variants']]
        self.assertEqual({v['id'] for v in variants},{'L000','L006'})
        self.assertTrue(all(v['passed_selection'] is None for v in variants))

    def test_iterative_promotion_and_cross_run_escape(self):
        name='run_001_cycle_00'; directory=self.root/'run_001/cycle_00/protenix-mini/predictions'
        self.files(directory,name+'_sample_0.pdb',name+'_summary_confidence_sample_0.json')
        live.publish(directory,name,'protenix',live.pairs_in(directory,'protenix',name))
        overview=catalog._iterative_overview(self.root,100)
        self.assertEqual(len(overview['groups']),1)
        (self.root/'run_001/metrics_per_cycle.csv').write_text('cycle,structure_path,iptm\n0,'+str(directory/(name+'_sample_0.pdb'))+',0.85\n')
        (self.root/'studio_run.json').write_text('{"arguments":["--predictor","protenix-mini"]}')
        rows=catalog._iterative_rows(self.root)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['iptm'],'0.85')
        receipt=next((self.root/'.studio_live_results').glob('*.json'))
        doc=json.loads(receipt.read_text());doc['artifacts'][0]['structure']='../outside.pdb';receipt.write_text(json.dumps(doc))
        self.assertEqual(records(self.root),[])

if __name__=='__main__': unittest.main()
