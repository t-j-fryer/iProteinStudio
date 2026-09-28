"""Combined MCP views preserve child identity, filters, limits and safe paths."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/mcp'))
from iprotein_mcp import catalog, common
from server import MCPServer


class BatchResults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, IPROTEINSTUDIO_TEST_SUPPORT_ROOT=str(self.root),
                              IPROTEINSTUDIO_AGENT_ROOT=str(self.root / 'agent'))
        self.env.start()
        workspace = self.root / 'projects/demo'; workspace.mkdir(parents=True)
        self.batch = workspace / 'engine-batch-test'; self.batch.mkdir()
        for name in ['first', 'second']:
            child = workspace / name; child.mkdir()
            (child / 'model.cif').write_text('data_fixture')
            (child / 'studio_run.json').write_text(json.dumps({'request': {'scaffoldID': name, 'numDesigns': 100, 'numCycles': 5, 'designPredictor': 'boltz'}}))
            (child / 'comparison_scores_long.csv').write_text('run,cycle,stage,predictor,structure_path,iptm,is_hit\n1,0,design,boltz,model.cif,0.8,\n1,1,post,boltz,model.cif,0.9,true\n')
        (self.batch / 'studio_engine_batch.json').write_text(json.dumps({'campaigns': ['/old/workspace/first', '/old/workspace/second']}))

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_discovery_filters_and_owner_relative_artifacts(self):
        runs = catalog.list_runs('demo')
        self.assertIn('iterative_batch', [r['workflow'] for r in runs])
        result = MCPServer('read').tool_call('results_overview', {'run_id': 'demo/engine-batch-test'})
        self.assertEqual(result['requested_trajectories'], 200)
        self.assertEqual(result['expected_optimized_cycle_outputs'], 1000)
        self.assertEqual(len({g['id'] for g in result['groups']}), 2)
        self.assertEqual({g['artifact_run_id'] for g in result['groups']}, {'demo/first', 'demo/second'})
        filtered = catalog.results_overview('demo/engine-batch-test', framework_id='second', design_engine='boltz')
        self.assertEqual(len(filtered['groups']), 1)
        self.assertEqual(filtered['groups'][0]['framework_id'], 'second')
        self.assertTrue(catalog.results_overview('demo/engine-batch-test', limit=1)['truncated'])
        self.assertFalse(filtered['truncated'])
        self.assertEqual(len(catalog.results_overview('demo/engine-batch-test', hit_only=True)['groups']), 2)
        self.assertEqual(catalog.results_overview('demo/engine-batch-test', design_engine='missing')['groups'], [])

    def test_missing_or_escaping_children_fail_loudly(self):
        child = self.root / 'projects/demo/first'
        child.rename(self.root / 'outside')
        child.symlink_to(self.root / 'outside', target_is_directory=True)
        with self.assertRaises(common.StudioError): catalog.results_overview('demo/engine-batch-test')
        child.unlink()
        with self.assertRaises(common.StudioError): catalog.results_overview('demo/engine-batch-test')

    def test_live_prediction_visible_before_cycle_end_and_superseded(self):
        child = self.root / 'projects/demo/first'
        (child / 'comparison_scores_long.csv').unlink()
        cycle = child / 'run_001/cycle_00'; cycle.mkdir(parents=True)
        (child / 'confidence.json').write_text('{"iptm": 0.8}')
        header = 'cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json\n'
        row = '0,0.8,0.9,ACDE,model.cif,confidence.json\n'
        (cycle / 'live_prediction.csv.part').write_text(header + row)
        self.assertEqual(catalog._iterative_rows(child), [])
        (cycle / 'live_prediction.csv.part').rename(cycle / 'live_prediction.csv')
        rows = catalog._iterative_rows(child)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['binder_sequence'], 'ACDE')
        self.assertEqual(len(catalog.results_overview('demo/first')['groups']), 1)
        (cycle.parent / 'metrics_per_cycle.csv').write_text(header + row.replace('0.8', '0.85'))
        rows = catalog._iterative_rows(child)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['iptm'], '0.85')


if __name__ == '__main__': unittest.main()
