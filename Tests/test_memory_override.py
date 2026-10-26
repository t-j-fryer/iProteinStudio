"""Explicit memory overrides survive plan/dispatch boundaries; no model inference."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0] = [str(ROOT / 'Tests'), str(PIPELINE / 'scripts'), str(PIPELINE / 'mcp')]
from test_memory_admission import config, machine
import memory_admission as memory
from iprotein_mcp import broker, common, plans, memory as bridge
from iprotein_mcp.desktop import desktop_plan
from iprotein_mcp.memory_sampling import Sampler, process_memory


class OverrideTests(unittest.TestCase):
    def test_preserves_rejected_estimate_and_reason(self):
        cfg = config(916, 'openfold-3-mlx')
        normal = memory.assess(cfg, machine())
        override = memory.assess({**cfg, 'memory_policy':'override'}, machine())
        self.assertEqual(normal['status'], 'blocked')
        self.assertEqual(override['status'], 'overridden')
        self.assertEqual(override['would_be_status'], normal['status'])
        self.assertEqual(override['estimated_gib'], normal['estimated_gib'])
        self.assertEqual(override['original_message'], normal['message'])
        self.assertEqual(memory.assess({**cfg, 'memory_policy':'override'}, {}, live=True)['status'], 'overridden')
        with self.assertRaises(ValueError): memory.assess({**cfg, 'memory_policy':True}, machine())

    def test_all_unqualified_routes_and_context_restoration(self):
        for kind in ('rfd3_deNovo', 'desktop_nise', 'desktop_motif_beta'):
            request = {'request':{'stage':'cycles'}, 'memory_policy':'override'}
            result = bridge.check_plan(kind, request, live=True)
            self.assertEqual(result['status'], 'overridden')
            self.assertIsNone(result['estimated_gib'])
            with self.assertRaises(common.StudioError): bridge.check_plan(kind, {'request':{'stage':'cycles'}})
        @bridge.memory_request
        def nested(args):
            self.assertNotIn('memory_policy', args)
            return bridge.requested_policy()
        self.assertEqual(nested({'memory_policy':'override'}), 'override')
        self.assertEqual(nested({}), 'enforce')
        with self.assertRaises(common.StudioError): nested({'memory_policy':'off'})
        self.assertEqual(bridge.POLICY.get(), 'enforce')

    def test_native_and_mcp_override_are_frozen_but_other_validation_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output = root/'projects/demo/prediction_runs/native'; output.mkdir(parents=True)
            scripts = root/'rfd3_scripts'; scripts.mkdir()
            (scripts/'predict_batch.py').write_text('print("inert")\n')
            cfg = config(916, 'openfold-3-mlx'); cfg['output'] = str(output)
            (output/'prediction_config.json').write_text(json.dumps(cfg))
            with patch.dict(os.environ, NANOHUNTER_ROOT=str(root), IPROTEINSTUDIO_AGENT_ROOT=str(root/'agent')), \
                 patch.object(bridge,'contract',return_value=memory), patch.object(memory,'machine_memory',return_value=machine()):
                for plan in (plans.prediction_plan({'project':'demo','request':cfg,'memory_policy':'override'}),
                             desktop_plan({'project':'demo','workflow':'prediction','output':str(output),'memory_policy':'override'})):
                    self.assertEqual(plan['normalized_request']['memory_policy'], 'override')
                    self.assertEqual(plan['normalized_request']['memory_admission']['would_be_status'], 'blocked')
                    self.assertEqual(plans.load_plan(plan['id'],plan['sha256'])['sha256'],plan['sha256'])
                    self.assertEqual(bridge.check_saved_plan(plan)['status'], 'overridden')
                bad = {**cfg,'predictors':['missing-model']}
                with self.assertRaises(common.StudioError): plans.prediction_plan({'project':'demo','request':bad,'memory_policy':'override'})

    def test_worker_dispatches_override_and_records_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan={'id':'plan-test','sha256':'test','kind':'prediction',
                  'normalized_request':{'config':config(), 'memory_policy':'override'}}
            old_signals={s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
            try:
                with patch.dict(os.environ,NANOHUNTER_ROOT=str(root),IPROTEINSTUDIO_AGENT_ROOT=str(root/'agent')), \
                     patch.object(broker,'load_plan',return_value=plan), patch.object(bridge,'contract',return_value=memory), \
                     patch.object(memory,'machine_memory',return_value=machine(available=1)), \
                     patch('iprotein_mcp.process_tree.snapshot',return_value={os.getpid():{'born':'now'}}), \
                     patch.object(broker,'_execute_prediction',return_value=0) as execute:
                    path=broker.state_path('job-test')
                    common.atomic_json(path,{'pid':os.getpid(),'status':'queued'})
                    common.atomic_json(path.parent/'plan.json',plan)
                    self.assertEqual(broker.run_worker('job-test'),0)
                    execute.assert_called_once()
                    self.assertEqual(common.load_json(path)['memory_admission']['status'],'overridden')
            finally:
                for sig,handler in old_signals.items(): signal.signal(sig,handler)
                broker._MEMORY_POLICY='enforce'

    def test_child_prediction_admission_inherits_recorded_policy(self):
        with patch.dict(os.environ,IPROTEINSTUDIO_MEMORY_POLICY='override'), patch.object(memory,'machine_memory',return_value={}):
            self.assertEqual(memory.require(config(),live=True)['status'],'overridden')

    def test_mcp_schema_exposes_choice_and_rejects_invalid_value(self):
        import server
        from iprotein_mcp.common import validate_schema
        for name in ('prediction_plan','rfd3_motif_scaffolding_plan','nise_plan','pipeline_recipe_plan','iterative_batch_plan'):
            prop=server.TOOLS[name]['inputSchema']['properties']['memory_policy']
            self.assertEqual(prop['default'],'enforce')
            self.assertEqual(prop['enum'],['enforce','override'])
            with self.assertRaises(common.StudioError): validate_schema('silently-off',prop)

    def test_real_child_receives_override_and_sampler_records_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.dict(os.environ,NANOHUNTER_ROOT=str(root),IPROTEINSTUDIO_AGENT_ROOT=str(root/'agent')), \
                 patch.object(broker,'_MEMORY_POLICY','override'), patch.object(broker,'_RUNTIME_BINDINGS',{}), \
                 patch.object(broker,'_CODE_SNAPSHOT',None), patch.object(broker,'_EXECUTION_FD',None):
                path=broker.state_path('job-inert')
                common.atomic_json(path,{'status':'running','stage':'inert-test'})
                script='import os,time; assert os.environ["IPROTEINSTUDIO_MEMORY_POLICY"] == "override"; time.sleep(1.2)'
                self.assertEqual(broker._run_logged('job-inert',[sys.executable,'-c',script],root,dict(os.environ)),0)
                result=common.load_json(path)
                summary=common.load_json(Path(result['memory_summary']))
                self.assertEqual(summary['policy'],'override')
                self.assertGreaterEqual(summary['samples'],1)
                self.assertEqual(summary['exit_code'],0)
                self.assertTrue(Path(result['memory_samples']).is_file())

    def test_native_counter_and_missing_samples_remain_distinct(self):
        if sys.platform != 'darwin': self.skipTest('Darwin counters')
        current=process_memory(os.getpid())
        self.assertGreater(current['rss_bytes'],0)
        class Family:
            def alive(self): return {os.getpid():{}}
        with tempfile.TemporaryDirectory() as tmp:
            sampler=Sampler(tmp,'override',['inert-test'])
            sampler.sample(Family(),'unit-test')
            sampler.finish(0)
            row=json.loads(sampler.path.read_text().splitlines()[0])
            self.assertTrue(row['complete'])
            self.assertGreater(row['tree_footprint_bytes'],0)
            sampler.last=-float('inf')
            with patch('iprotein_mcp.memory_sampling.process_memory',return_value=None): sampler.sample(Family(),'missing')
            missing=json.loads(sampler.path.read_text().splitlines()[-1])
            self.assertIsNone(missing['tree_rss_bytes'])
            self.assertFalse(missing['complete'])


if __name__=='__main__': unittest.main()
