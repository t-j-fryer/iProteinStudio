"""Exercise real frozen plans, fit selection and explicit queue confirmation; no inference."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0] = [str(PIPELINE/'mcp'), str(PIPELINE/'scripts')]
from iprotein_mcp import common, memory_estimate as estimate, submission, plans
import memory_admission

PACK = json.loads(estimate.MODELS_PATH.read_text())
DEFAULTS = json.loads((PIPELINE/'scripts/prediction_profiles.json').read_text())


def config(length=500, engine='esmfold2-full-mlx', **extra):
    return dict(jobs=[dict(chains=[dict(id='A', kind='protein', sequence='A'*length, msa='auto')])],
                predictors=[engine], **extra)


def report(cfg, gib=64):
    return estimate.for_plan(dict(kind='prediction', normalized_request=dict(config=cfg)),
                             machine=dict(total_bytes=gib*1024**3))


class EstimateTests(unittest.TestCase):
    def test_all_chain_copies_and_measured_peak_allowance(self):
        cfg=config(250);cfg['jobs'][0]['chains'][0]['copies']=2
        old=copy.deepcopy(cfg);r=report(cfg)
        self.assertEqual(r['largest_complex_aa'],500)
        self.assertEqual(r['details'][0]['chain_copies'],2)
        self.assertAlmostEqual(r['details'][0]['median_request_peak_gib'],25.13,places=2)
        self.assertAlmostEqual(r['estimated_peak_gib'],27.44,places=2)
        self.assertEqual(cfg,old)
        self.assertNotIn('torch',sys.modules);self.assertNotIn('mlx',sys.modules)

    def test_larger_assembly_and_600m_profiles_stay_separate(self):
        cfg=config(847,'esmfold2-600-mlx',prediction_settings={'esmfold2-600-mlx':dict(chunk_size=32,cache_limit_mib=512)})
        cfg['jobs'][0]['chains'][0]['copies']=2
        r=report(cfg);self.assertEqual(r['largest_complex_aa'],1694)
        self.assertAlmostEqual(r['estimated_peak_gib'],39.46,places=2)
        self.assertFalse(r['details'][0]['extrapolation'])
        standard=config(500,'esmfold2-600-mlx',prediction_settings={'esmfold2-600-mlx':dict(chunk_size=0,cache_limit_mib=4096)})
        self.assertEqual(report(standard)['details'][0]['model_id'],'esm600_standard_bf16__process_footprint')
        self.assertIsNone(report(config(500,'esmfold2-600-mlx'))['estimated_peak_gib'])

    def test_extrapolation_and_settings_mismatch_are_explicit(self):
        r=report(config(2000));self.assertTrue(r['warning']);self.assertTrue(r['details'][0]['extrapolation'])
        for kwargs in [dict(diffusion_samples=2),dict(template={'path':'unused'}),
                       dict(prediction_settings={'esmfold2-full-mlx':dict(recycles=1)}),
                       dict(prediction_settings={'esmfold2-full-mlx':dict(chunk_size=32)})]:
            r=report(config(**kwargs));self.assertIsNone(r['estimated_peak_gib']);self.assertTrue(r['partial'])
        with patch.dict(os.environ,IPROTEINSTUDIO_ESMFOLD2_TRUNK_DTYPE='float32'):
            self.assertIsNone(report(config())['estimated_peak_gib'])

    def test_batches_are_sequential_engines_are_not_added(self):
        cfg=config(engine='boltz',max_parallel=1,batch_size=8)
        single=report(cfg)['estimated_peak_gib'];cfg['jobs']*=8
        self.assertEqual(report(cfg)['estimated_peak_gib'],single)
        cfg['max_parallel']=2;cfg['batch_size']=1
        self.assertAlmostEqual(report(cfg)['estimated_peak_gib'],single*2,places=1)
        cfg['predictors']=['boltz','esmfold2-full-mlx'];cfg['max_parallel']=1
        r=report(cfg);self.assertEqual(r['estimated_peak_gib'],max(x['estimated_peak_gib'] for x in r['details']))

    def test_longest_binder_and_all_target_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            common.atomic_json(out/'rfd4_config.json',dict(settings=dict(task='protein',length=100,length_plan={'minimum':100,'maximum':200},
                predictor='esmfold2-full-mlx',search='beam',target_msa='target.a3m'),target_sequences={'B':'A'*150,'C':'A'*150}))
            r=estimate.for_plan(dict(kind='desktop_rfd4',normalized_request={'output':str(out)}),{'total_bytes':64*1024**3})
            self.assertEqual(r['largest_complex_aa'],500)
            self.assertTrue(r['partial'])
            self.assertEqual(r['details'][1]['median_request_peak_gib'],25.13)
            self.assertIsNone(r['details'][0]['estimated_peak_gib'])
            self.assertIn('total workflow may peak higher',estimate.describe(r))

    def test_design_templates_count_id_lists_and_maximum_binder(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'template.json'
            p.write_text(json.dumps({'sequences':[{'protein':{'id':['B','C'],'sequence':'A'*150,'msa':'target.a3m'}}]}))
            n=dict(arguments=['--template-yaml',str(p),'--binder-max-len','200','--predictor','esmfold2-full-mlx','--max-parallel','1'])
            r=estimate.for_plan(dict(kind='desktop_iterative',normalized_request=n),{'total_bytes':64*1024**3})
            self.assertEqual(r['largest_complex_aa'],500)
            self.assertEqual(r['details'][0]['chain_copies'],3)

    def test_unsupported_chemistry_and_missing_models_remain_reviewable(self):
        cfg=config();cfg['jobs'][0]['chains'].append(dict(kind='ligand',sequence='not-a-protein'))
        r=report(cfg);self.assertIsNone(r['estimated_peak_gib']);self.assertTrue(r['warning'])
        with patch.object(estimate,'MODELS_PATH',Path('/missing/model.json')):
            r=report(config());self.assertIsNone(r['estimated_peak_gib']);self.assertTrue(r['partial'])
        text=estimate.describe(r);self.assertIn('Proceed',text);self.assertNotIn('guaranteed maximum',text)

    def test_rfd3_counts_selected_target_chains_without_inventing_ram(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'config').mkdir();pdb=out/'target.pdb'
            lines=[]
            for index,(chain,residue) in enumerate([('B',1),('B',2),('C',1),('D',1)],1):
                lines.append(f'ATOM  {index:5d}  CA  ALA {chain}{residue:4d}    {0:8.3f}{0:8.3f}{0:8.3f}{1:6.2f}{80:6.2f}           C\n')
            pdb.write_text(''.join(lines))
            common.atomic_json(out/'config/studio_request.json',dict(target_kind='protein',design_mode='deNovo',
                target_structure=str(pdb),target_chains=['B','C'],lengths=[40,60]))
            r=estimate.for_plan(dict(kind='desktop_rfdiffusion3',normalized_request={'output':str(out)}),{'total_bytes':64*1024**3})
            self.assertEqual(r['largest_complex_aa'],63)
            self.assertIsNone(r['estimated_peak_gib']);self.assertTrue(r['partial'])

    def test_nanobody_uses_longest_actual_selected_framework(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'scaffold_inputs/long').mkdir(parents=True)
            common.atomic_json(out/'framework_identity.json',{'sequence':'A'*120})
            common.atomic_json(out/'scaffold_inputs/long/framework_identity.json',{'sequence':'A'*135})
            common.atomic_json(out/'rfd4_config.json',dict(settings=dict(task='nanobody',length=20,predictor='esmfold2-full-mlx',
                search='beam',target_msa='target.a3m'),target_sequences={'B':'A'*150}))
            r=estimate.for_plan(dict(kind='desktop_rfd4',normalized_request={'output':str(out)}),{'total_bytes':64*1024**3})
            self.assertEqual(r['largest_complex_aa'],285)


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'projects/demo/prediction_runs/test';self.out.mkdir(parents=True)
        (self.root/'rfd3_scripts').mkdir();(self.root/'rfd3_scripts/predict_batch.py').write_text('raise AssertionError("must not run")\n')
        cfg=config(900);cfg['output']=str(self.out)
        common.atomic_json(self.out/'prediction_config.json',cfg)
        env=patch.dict(os.environ,NANOHUNTER_ROOT=str(self.root),IPROTEINSTUDIO_AGENT_ROOT=str(self.root/'agent'))
        env.start();self.addCleanup(env.stop)
        fixture=patch('iprotein_mcp.memory.contract',return_value=memory_admission)
        fixture.start();self.addCleanup(fixture.stop)
        hardware=patch.object(memory_admission,'machine_memory',return_value={'total_bytes':8*1024**3})
        hardware.start();self.addCleanup(hardware.stop)
        self.request=dict(project='demo',workflow='prediction',output=str(self.out))

    def test_preview_queues_nothing_and_confirmation_binds_same_plan(self):
        with patch('iprotein_mcp.broker.start_job',return_value={'id':'job-inert','status':'queued'}) as start:
            review=submission.submit(self.request,prepare_only=True)
            start.assert_not_called()
            self.assertFalse((self.out/'studio_job.json').exists())
            saved=plans.load_plan(review['plan_id'],review['plan_sha256'])
            self.assertEqual(saved['normalized_request']['memory_policy'],'override')
            retained=Path(saved['code_snapshot']['path'])/'mcp/iprotein_mcp/memory_estimate_models.json'
            self.assertEqual(retained.read_bytes(),estimate.MODELS_PATH.read_bytes())
            self.assertGreater(json.loads((self.out/'studio_memory_review.json').read_text())['report']['estimated_peak_gib'],8)
            state=submission.confirm(review['plan_id'],review['plan_sha256'],review['report_sha256'])
            self.assertEqual(state['id'],'job-inert')
            start.assert_called_once_with(saved['id'],saved['sha256'])
            consent=common.load_json(self.out/'studio_memory_confirmation.json')
            self.assertEqual(consent['report_sha256'],review['report_sha256'])
            self.assertEqual(consent['choice'],'proceed')

    def test_changed_review_or_changed_input_cannot_use_old_confirmation(self):
        review=submission.submit(self.request,prepare_only=True)
        p=self.out/'studio_memory_review.json';j=common.load_json(p);j['report']['estimated_peak_gib']=.1;common.atomic_json(p,j)
        with patch('iprotein_mcp.broker.start_job') as start:
            with self.assertRaises(common.StudioError):submission.confirm(review['plan_id'],review['plan_sha256'],review['report_sha256'])
            start.assert_not_called()
        review=submission.submit(self.request,prepare_only=True)
        saved=plans.load_plan(review['plan_id'],review['plan_sha256'])
        (Path(saved['code_snapshot']['path'])/'rfd3_scripts/predict_batch.py').write_text('print("changed frozen code")\n')
        with patch('iprotein_mcp.broker.start_job') as start:
            with self.assertRaises(common.StudioError):submission.confirm(review['plan_id'],review['plan_sha256'],review['report_sha256'])
            start.assert_not_called()

    def test_headless_enforcement_still_rejects_oversized_work_without_choice(self):
        with patch('iprotein_mcp.broker.start_job') as start:
            with self.assertRaises(common.StudioError):submission.submit(self.request)
            start.assert_not_called()


if __name__=='__main__':unittest.main()
