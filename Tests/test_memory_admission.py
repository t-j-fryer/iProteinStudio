"""Memory policy and real broker boundaries, without allocating model tensors."""
import copy
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0, str(PIPELINE / 'scripts'))
sys.path.insert(0, str(PIPELINE / 'mcp'))
import memory_admission as memory
from iprotein_mcp import plans, broker, common
from iprotein_mcp import memory as bridge_memory
from iprotein_mcp.desktop import desktop_plan


def config(length=164, engine='boltz', count=1, **kwargs):
    return dict(predictors=[engine], jobs=[dict(name=f'protein-{i}', chains=[
        dict(id='A', kind='protein', sequence='A' * length, msa='auto')]) for i in range(count)], **kwargs)


def machine(gib=64, available=48, pressure=1):
    return dict(total_bytes=int(gib * memory.GIB), available_bytes=int(available * memory.GIB), pressure=pressure)


class MemoryTests(unittest.TestCase):
    def test_physical_budget_allow_warn_block(self):
        cfg = config()
        estimate = memory.assess(cfg, machine())['estimated_gib']
        self.assertEqual(memory.assess(cfg, machine())['status'], 'allowed')
        self.assertEqual(memory.assess(cfg, machine(estimate + 4.2))['status'], 'warning')
        self.assertEqual(memory.assess(cfg, machine(8))['status'], 'blocked')

    def test_dimer_counts_both_copies(self):
        cfg = config(458, 'openfold-3-mlx')
        cfg['jobs'][0]['chains'].append(dict(id='B', kind='protein', sequence='A'*458))
        result = memory.assess(cfg, machine())
        self.assertEqual(result['details'][0]['largest_input'], 916)
        self.assertEqual(result['status'], 'blocked')
        self.assertGreater(result['estimated_gib'], 78.51)

    def test_yaml_chain_lists_cannot_hide_copies(self):
        for chain_id in (['A','B'], '[A,B]', 'A\n      sequence: WWW'):
            cfg = config(458)
            cfg['jobs'][0]['chains'][0]['id'] = chain_id
            self.assertEqual(memory.assess(cfg,machine())['status'],'blocked')

    def test_no_inference_and_input_not_changed(self):
        cfg = config(); original = copy.deepcopy(cfg)
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('no subprocess expected')):
            result = memory.assess(cfg, machine())
        self.assertEqual(result['status'], 'allowed')
        self.assertEqual(cfg, original)
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('mlx', sys.modules)

    def test_all_calibration_maxima_bounded(self):
        for engine, profile in memory.DATA['profiles'].items():
            for anchor in profile['anchors']:
                n = anchor['tokens']
                raw = profile['base_gib'] + profile['quadratic_gib']*n*n + profile['cubic_bytes']*n**3/memory.GIB
                self.assertGreaterEqual(raw + 1e-6, anchor['peak_gib'], (engine, n))

    def test_estimate_monotonic_and_finite(self):
        for engine, profile in memory.DATA['profiles'].items():
            previous = 0
            for length in (1, 96, 164, 370):
                cfg = config(length, engine, diffusion_samples=1)
                estimate = memory.estimate_job(engine, cfg['jobs'][0], cfg)['estimated_gib']
                self.assertGreaterEqual(estimate, previous)
                previous = estimate

    def test_seeds_and_sequential_batches_do_not_multiply_memory(self):
        single = memory.assess(config(96), machine())
        many = memory.assess(config(96, count=1000, num_seeds=20, batch_size=1000), machine())
        self.assertEqual(single['estimated_gib'], many['estimated_gib'])

    def test_concurrent_workers_and_chunks_counted(self):
        one = memory.assess(config(96, 'intellifold', count=16), machine())
        four = memory.assess(config(96, 'intellifold', count=64), machine())
        self.assertAlmostEqual(4*one['estimated_gib'], four['estimated_gib'], delta=.03)
        one_explicit = memory.assess(config(96, 'intellifold', count=64, max_parallel=1), machine())
        self.assertEqual(one['estimated_gib'], one_explicit['estimated_gib'])

    def test_engines_and_buckets_are_sequential(self):
        cfg = config(96, count=16)
        cfg['predictors'] = ['boltz', 'intellifold']
        cfg['jobs'] += config(370, count=16)['jobs']
        result = memory.assess(cfg, machine())
        self.assertEqual(result['estimated_gib'], max(d['estimated_gib'] for d in result['details']))

    def test_full_and_flash_are_distinct(self):
        flash = memory.assess(config(370, 'intellifold'), machine())
        full = memory.assess(config(370, 'intellifold', intellifold_model='v2'), machine())
        self.assertGreater(full['estimated_gib'], flash['estimated_gib'])

    def test_atom_rich_sequences_and_unknown_design_residues_cost_more(self):
        small = config(164)
        large = copy.deepcopy(small); large['jobs'][0]['chains'][0]['sequence'] = 'W'*164
        unknown = copy.deepcopy(small); unknown['jobs'][0]['chains'][0]['sequence'] = 'X'*164
        self.assertGreater(memory.assess(large, machine())['estimated_gib'], memory.assess(small, machine())['estimated_gib'])
        self.assertEqual(memory.assess(large, machine())['estimated_gib'], memory.assess(unknown, machine())['estimated_gib'])

    def test_automatic_boltz_partner_potentials_are_not_missed(self):
        document = {'sequences':[{'protein':{'id':'A','sequence':'A'*65}},
                                 {'protein':{'id':'B','sequence':'A'*96}}]}
        with patch.object(bridge_memory,'read_template',return_value=document):
            cfg = bridge_memory.iterative_configs({'arguments':['--template-yaml','fixture','--predictor','boltz']})[0]
        self.assertTrue(cfg['use_potentials'])
        self.assertEqual(memory.assess(cfg,machine())['status'],'blocked')

    def test_pre_policy_saved_plan_cannot_start(self):
        plan = dict(kind='prediction',normalized_request={'config':config()})
        with patch.object(bridge_memory,'contract',return_value=memory), patch.object(memory,'machine_memory',return_value=machine()):
            with self.assertRaisesRegex(common.StudioError,'predates'):
                bridge_memory.check_saved_plan(plan)

    def test_design_parallelism_charges_repeated_largest_shape(self):
        cfg = config(96, memory_scope='resident-design', max_parallel=1)
        one = memory.assess(cfg,machine())['estimated_gib']
        cfg['max_parallel'] = 4
        four = memory.assess(cfg,machine())['estimated_gib']
        self.assertAlmostEqual(four-4, 4*(one-4), delta=.03)

    def test_design_initial_full_and_refinement_flash_remain_distinct(self):
        with patch.object(bridge_memory,'read_template',return_value={'sequences':[{'protein':{'id':'A','sequence':'A'*96}}]}):
            cfg = bridge_memory.iterative_configs({'arguments':['--template-yaml','fixture',
                '--predictor','intellifold','--model','v2-flash','--initialization-predictor','intellifold',
                '--initialization-model','v2']})[0]
        self.assertEqual(cfg['predictors'],['intellifold-full','intellifold'])

    def test_direct_predictor_blocks_before_msa_or_engine(self):
        spec = importlib.util.spec_from_file_location('memory_test_batch', ROOT/'Sources/iProteinStudio/Resources/rfd3/predict_batch.py')
        batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'scripts').symlink_to(PIPELINE/'scripts')
            cfg = config(916,'openfold-3-mlx'); cfg.update(root=str(root),output=str(root/'output'))
            path=root/'config.json'; path.write_text(json.dumps(cfg))
            with patch.object(sys,'argv',['predict_batch.py','--config',str(path)]), \
                 patch.dict(os.environ), patch.object(memory,'machine_memory',return_value=machine()), \
                 patch.object(batch,'resolve_msas',side_effect=AssertionError('MSA must not start')) as msa:
                with self.assertRaises(SystemExit) as error: batch.main()
                self.assertEqual(error.exception.code,1)
                msa.assert_not_called()

    def test_samples_include_engine_default(self):
        default = memory.assess(config(96, 'protenix-mini'), machine())
        one = memory.assess(config(96, 'protenix-mini', diffusion_samples=1), machine())
        self.assertAlmostEqual(default['estimated_gib'], 5*one['estimated_gib'], delta=.03)

    def test_unqualified_inputs_fail_closed(self):
        cases = [config(917), config(371, 'protenix-v2'), config(engine='unknown'),
                 config(use_potentials=True), config(template={'path':'x'}),
                 config(prediction_settings={'boltz': {'msa_depth':0}}),
                 config(prediction_settings={'boltz': {'msa_depth':129}})]
        ligand = config(); ligand['jobs'][0]['chains'].append({'kind':'ligand', 'smiles':'CC'})
        cases.append(ligand)
        for cfg in cases:
            self.assertEqual(memory.assess(cfg, machine())['status'], 'blocked', cfg)

    def test_single_sequence_does_not_require_msa_cap(self):
        cfg = config(prediction_settings={'boltz': {'msa_depth':0}})
        cfg['jobs'][0]['chains'][0]['msa'] = 'empty'
        self.assertEqual(memory.assess(cfg, machine())['status'], 'allowed')

    def test_missing_counters_fail_closed(self):
        for host in ({}, {'total_bytes':0}, {'total_bytes':True}):
            self.assertEqual(memory.assess(config(), host)['status'], 'blocked')
        self.assertEqual(memory.assess(config(), {'total_bytes':64*memory.GIB}, live=True)['status'], 'blocked')

    def test_dispatch_rechecks_actual_available_memory_and_pressure(self):
        for host in (machine(available=2), machine(pressure=2), machine(pressure=4)):
            self.assertEqual(memory.assess(config(), host, live=False)['status'], 'allowed')
            self.assertEqual(memory.assess(config(), host, live=True)['status'], 'blocked')

    def test_native_and_mcp_same_result_and_block_before_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root/'projects/demo/prediction_runs/native'; output.mkdir(parents=True)
            scripts = root/'rfd3_scripts'; scripts.mkdir()
            (scripts/'predict_batch.py').write_text('raise AssertionError("must not execute")\n')
            native = config(916, 'openfold-3-mlx'); native['output'] = str(output)
            (output/'prediction_config.json').write_text(json.dumps(native))
            with patch.dict(os.environ, {'NANOHUNTER_ROOT':str(root), 'IPROTEINSTUDIO_AGENT_ROOT':str(root/'agent')}), \
                 patch.object(bridge_memory, 'contract', return_value=memory), \
                 patch.object(memory, 'machine_memory', return_value=machine()), \
                 patch('iprotein_mcp.code_snapshot.capture', side_effect=AssertionError('must block before snapshot')):
                for operation in (lambda: plans.prediction_plan({'project':'demo','request':native}),
                                  lambda: desktop_plan({'project':'demo','workflow':'prediction','output':str(output)})):
                    with self.assertRaisesRegex(common.StudioError, 'Estimated model memory'):
                        operation()
            self.assertFalse((root/'agent/jobs').exists())

    def test_saved_native_config_and_live_check(self):
        with patch.object(bridge_memory, 'contract', return_value=memory), \
             patch.object(memory, 'machine_memory', side_effect=[machine(), machine(available=1)]):
            self.assertEqual(bridge_memory.check_plan('desktop_prediction', {'config':config()})['status'], 'allowed')
            with self.assertRaises(common.StudioError):
                bridge_memory.check_plan('desktop_prediction', {'config':config()}, live=True)

    def test_cli_returns_structured_block_without_models(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.json'; path.write_text(json.dumps(config(100000)))
            completed = subprocess.run([sys.executable, str(PIPELINE/'scripts/memory_admission.py'), '--config', str(path)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)['status'], 'blocked')

    def test_iterative_maximum_binder_and_independent_checkers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'template.yaml'
            path.write_text(json.dumps({'sequences':[
                {'protein':{'id':'A','sequence':'A'*10}},
                {'protein':{'id':'B','sequence':'A'*200}}]}))
            normalized = {'template_artifact':{'path':str(path)}, 'arguments':[
                '--workflow','protein','--predictor','boltz','--binder-max-len','120',
                '--max-parallel','1','--post-predictor','intellifold,esmfold2-fast-mlx', '--boltz-no-potentials']}
            configs = bridge_memory.configs_for_plan('iterative_design', normalized)
            self.assertEqual(configs[0]['predictors'], ['boltz','intellifold','esmfold2-fast-mlx'])
            self.assertTrue(all(memory.job_shape(c['jobs'][0]) == 320 for c in configs))
            normalized['arguments'] += ['--initialization-method','rfd3']
            with self.assertRaisesRegex(common.StudioError, 'RFdiffusion3'):
                bridge_memory.configs_for_plan('iterative_design', normalized)

    def test_unqualified_generation_and_ligand_routes_are_explicit(self):
        self.assertIsNone(bridge_memory.check_plan('desktop_motif_beta', {'request': {'stage': 'prepare'}}))
        for stage in ('backbones', 'cycles'):
            with self.assertRaisesRegex(common.StudioError, 'not yet qualified'):
                bridge_memory.check_plan('desktop_motif_beta', {'request': {'stage': stage}})
        for kind in ('rfd3_deNovo','desktop_rfdiffusion3','desktop_nise','desktop_nise_continuation'):
            with self.assertRaisesRegex(common.StudioError, 'not yet qualified'):
                bridge_memory.check_plan(kind, {})

    def test_worker_stops_before_execute_when_memory_changes_in_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = {'id':'plan-test', 'sha256':'test', 'kind':'prediction',
                    'normalized_request':{'config':config()}}
            env = {'NANOHUNTER_ROOT':str(root), 'IPROTEINSTUDIO_AGENT_ROOT':str(root/'agent')}
            before_signals = {s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
            try:
                with patch.dict(os.environ, env), \
                     patch.object(broker,'load_plan',return_value=plan), \
                     patch.object(bridge_memory,'contract',return_value=memory), \
                     patch.object(memory,'machine_memory',return_value=machine(available=1)), \
                     patch('iprotein_mcp.process_tree.snapshot',return_value={os.getpid():{'born':'now'}}), \
                     patch.object(broker,'_execute_prediction',side_effect=AssertionError('engine must not start')) as execute:
                    path = broker.state_path('job-test')
                    common.atomic_json(path, {'pid':os.getpid(),'status':'queued'})
                    common.atomic_json(path.parent/'plan.json', plan)
                    self.assertEqual(broker.run_worker('job-test'), 1)
                    self.assertEqual(json.loads(path.read_text())['status'], 'failed')
                    execute.assert_not_called()
            finally:
                for sig, handler in before_signals.items(): signal.signal(sig,handler)


if __name__ == '__main__':
    unittest.main()
