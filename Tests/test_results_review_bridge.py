"""Actual synthetic CPU analysis, immutable broker plan and local/remote exports."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0, str(PIPELINE/'mcp'))
from iprotein_mcp import review, exports, common, broker, plans
from server import MCPServer, TOOLS
from test_results_spatial import pose, policy

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'IPROTEINSTUDIO_TEST_SUPPORT_ROOT':str(self.root), 'NANOHUNTER_ROOT':str(self.root), 'IPROTEINSTUDIO_AGENT_ROOT':str(self.root/'agent')})
        env.start();self.addCleanup(env.stop)
        self.run = self.root/'projects/demo/rfd4_runs/fixture';self.run.mkdir(parents=True)
        common.atomic_json(self.run/'rfd4_config.json', {'settings':{}})
        self.source = self.run/'complex.pdb'; pose(self.source)
        self.records=[]
        for i,score in enumerate([.7,.8,.9,None]):
            metrics={'ipsae_min':score} if score is not None else {}
            artifact=dict(path='complex.pdb',path_sha256=common.file_digest(self.source),predictor='boltz',role='design',metrics=metrics)
            self.records.append(dict(candidate_id=f'{i:064x}',run_id='demo/rfd4_runs/fixture',group_id='family'+str(i//2),variant_id='proposal'+str(i),cycle=i%2,sequence='ACDEFG',is_hit=i==0,artifacts=[artifact]))
        indexed=patch.object(exports,'_index',side_effect=lambda _:json.loads(json.dumps(self.records)));indexed.start();self.addCleanup(indexed.stop)
        self.args=dict(run_id='demo/rfd4_runs/fixture',snapshot_sha256=common.canonical_digest(self.records))
    def test_metric_rules_ranking_family_caps_and_full_cycle_medians(self):
        result=MCPServer('read').tool_call('results_review',dict(self.args,mode='custom',rules=[dict(metric='ipsae_min',comparison='>=',threshold=.75)],max_per_family=1))
        self.assertEqual([r['metrics']['ipsae_min'] for r in result['candidates']],[.9,.8])
        self.assertEqual(result['metric'],'ipsae_min')
        self.assertEqual([(r['cycle'],r['count'],r['median']) for r in result['cycle_medians']],[(0,2,.8),(1,1,.8)])
        self.assertEqual(self.records[0]['is_hit'],True)
        self.assertEqual(review._scores({'metrics': {'complex_plddt': .85}})['complex_plddt'],85)
    def test_saved_and_missing_last_ascending(self):
        self.assertEqual(review.results_review(**self.args,mode='saved')['selected_count'],1)
        rows=review.results_review(**self.args,descending=False)['candidates']
        self.assertEqual([r['candidate_id'] for r in rows],[r['candidate_id'] for r in self.records])
    def test_catalog_retains_optional_scores_and_exact_native_feedback_pose(self):
        from iprotein_mcp import catalog
        scores=catalog._metrics(dict(run='1',cycle='2',ligand_plddt='80',pbind='0.6',custom_measured_score='4.2',is_hit='1',missing='nan'))
        self.assertEqual(scores,dict(ligand_plddt=80,pbind=.6,custom_measured_score=4.2))
        oracle=self.run/'oracle.pdb';oracle.write_bytes(self.source.read_bytes())
        row=dict(id='native',family='family0',structure='complex.pdb',oracle_structure='oracle.pdb',metrics={'ipsae_min':.8},design_metrics={'ptm':.4},oracle_engine='esmfold2-full-mlx')
        with patch.object(catalog,'_rfd4_rows',return_value=[row]):
            result=catalog.results_overview(self.args['run_id'])
        artifacts=result['groups'][0]['variants'][0]['artifacts']
        self.assertNotIn('ipsae_min',artifacts[0]['metrics'])
        self.assertEqual(artifacts[1]['metrics']['ipsae_min'],.8)
        self.assertEqual(artifacts[1]['predictor'],'esmfold2-full-mlx')
    def test_combined_score_never_crosses_assessments(self):
        self.records[0]['artifacts'][0]['metrics']={'pbind':.5,'ligand_plddt':80}
        self.records[1]['artifacts'] += [dict(path='complex.pdb',role='complex_reprediction',predictor='boltz',metrics={'ligand_plddt':90})]
        self.records[1]['artifacts'][0]['metrics']={'pbind':.9}
        result=review.results_review(run_id=self.args['run_id'])
        self.assertEqual(result['metric'],'boltz_combined_score')
        byid={r['candidate_id']:r for r in result['candidates']}
        self.assertEqual(byid[self.records[0]['candidate_id']]['metrics']['boltz_combined_score'],1.3)
        self.assertNotIn('boltz_combined_score',byid[self.records[1]['candidate_id']]['metrics'])
    def test_snapshot_pagination_and_changes(self):
        page=review.results_review(**self.args,limit=2)
        self.assertEqual(page['next_offset'],2)
        self.assertEqual(len(review.results_review(**self.args,offset=2)['candidates']),2)
        with self.assertRaises(common.StudioError):review.results_review(run_id=self.args['run_id'],offset=2)
        self.records[0]['sequence']='CHANGE'
        with self.assertRaisesRegex(common.StudioError,'changed'):review.results_review(**self.args)
    def archive(self,result):
        chunk=exports.export_read(result['export_sha256']);data=base64.b64decode(chunk['data_base64'])
        self.assertEqual(hashlib.sha256(data).hexdigest(),result['export_sha256'])
        return zipfile.ZipFile(io.BytesIO(data))
    def test_complete_csv_export_and_formula_protection(self):
        self.records[0]['group_id']='=spreadsheet()'
        result=MCPServer('run').tool_call('results_review_export',{'run_id':self.args['run_id']})
        with self.archive(result) as archive:
            csv=archive.read('designs.csv').decode();self.assertIn("'=spreadsheet()",csv)
            self.assertEqual(len(csv.splitlines()),5)
            self.assertEqual(len(json.loads(archive.read('review.json'))['candidates']),4)
    def test_portable_style_exact_source_and_safe_chains(self):
        result=review.viewer_script_export(**self.args,candidate_id=self.records[0]['candidate_id'],emphasized_chains='A')
        with self.archive(result) as archive:
            script=archive.read('manuscript_style.py').decode();compile(script,'manuscript_style.py','exec')
            self.assertIn("Path(__file__).resolve().parent",script)
            self.assertIn(self.records[0]['artifacts'][0]['path_sha256'],script)
            self.assertEqual(archive.read('structure.pdb'),self.source.read_bytes())
        with self.assertRaises(common.StudioError):review.viewer_script_export(**self.args,candidate_id=self.records[0]['candidate_id'],emphasized_chains='A;close all')
        self.source.write_text('changed')
        with self.assertRaises(common.StudioError):review.viewer_script_export(**self.args,candidate_id=self.records[0]['candidate_id'])
    def test_style_recipe_matches_native_generator(self):
        swift=(ROOT/'Sources/iProteinStudio/Core/ChimeraXPublicationStyle.swift').read_text()
        body=swift.split('return """\n',1)[1].split('\n        """',1)[0]
        expected='\n'.join(line[8:] for line in body.splitlines()).replace(r'\(literal)','__STUDIO_CONFIG_JSON_LITERAL__')+'\n'
        self.assertEqual(expected,(PIPELINE/'mcp/templates/chimerax_manuscript_v1.py.txt').read_text())
    def test_profiles_validation_and_cli_discovery(self):
        for name in ('results_review_export','viewer_script_export','results_spatial_plan'):
            with self.assertRaises(common.StudioError):MCPServer('read').tool_call(name,{})
        with self.assertRaises(common.StudioError):MCPServer('read').tool_call('results_review',dict(self.args,mode='custom',rules=[dict(metric='ipsae_min',comparison='>=',threshold=float('nan'))]))
        call=subprocess.run([sys.executable,'-B',str(PIPELINE/'mcp/studioctl.py'),'tools','--profile','run'],capture_output=True,text=True,check=True)
        self.assertIn('results_spatial_plan',[t['name'] for t in json.loads(call.stdout)['tools']])
        self.assertNotIn('engine_install_plan',[t['name'] for t in json.loads(call.stdout)['tools']])
        request=self.root/'request.json';request.write_text('{}')
        called=subprocess.run([sys.executable,'-B',str(PIPELINE/'mcp/studioctl.py'),'call','pipeline_catalog',str(request)],capture_output=True,text=True,check=True)
        self.assertIsInstance(json.loads(called.stdout),dict)
        refused=subprocess.run([sys.executable,'-B',str(PIPELINE/'mcp/studioctl.py'),'call','results_review_export',str(request)],capture_output=True,text=True)
        self.assertEqual(refused.returncode,2)
        self.assertIn('read profile',refused.stderr)
        request.write_text('{invalid')
        malformed=subprocess.run([sys.executable,'-B',str(PIPELINE/'mcp/studioctl.py'),'call','pipeline_catalog',str(request)],capture_output=True,text=True)
        self.assertEqual(malformed.returncode,2)
        self.assertNotIn('Traceback',malformed.stderr)
    def spatial_plan(self):
        python=self.root/'venvs/NanoHunter_boltz/bin/python';python.parent.mkdir(parents=True);python.symlink_to(sys.executable)
        return MCPServer('run').tool_call('results_spatial_plan',dict(self.args,candidate_ids=[self.records[0]['candidate_id']],policy=policy(cutoff='9')))
    def test_spatial_immutable_plan_and_actual_broker_execution(self):
        plan=self.spatial_plan()
        self.assertEqual(plan['kind'],'results_spatial');self.assertEqual(plan['resource_class'],'cpu_analysis')
        self.assertEqual(plan['normalized_request']['memory_policy'],'enforce')
        job=broker.start_job(plan['id'],plan['sha256'])
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            state=broker.load_state(job['id'])
            if state['status'] in broker.TERMINAL and not common.process_alive(state.get('pid')):break
            time.sleep(.2)
        self.assertEqual(state['status'],'completed',state)
        result=review.results_review(**self.args,spatial_job_id=job['id'])
        self.assertEqual(result['selected_count'],1)
        self.assertEqual(result['candidates'][0]['metrics']['spatial_maximum_distance'],9)
        receipt=Path(result['candidates'][0]['spatial']['receipt']);receipt.write_text('{}')
        with self.assertRaisesRegex(common.StudioError,'receipt'):review.results_review(**self.args,spatial_job_id=job['id'])
    def test_spatial_source_change_invalidates_plan(self):
        plan=self.spatial_plan();self.source.write_text('changed')
        with self.assertRaises(common.StudioError):plans.load_plan(plan['id'],plan['sha256'])
    def test_spatial_wrong_policy_no_predictor_or_geometry_fallback(self):
        with self.assertRaises(common.StudioError):MCPServer('run').tool_call('results_spatial_plan',dict(self.args,candidate_ids=[self.records[0]['candidate_id']],policy=policy(cutoff='NaN')))
        with self.assertRaisesRegex(common.StudioError,'receipt'):MCPServer('run').tool_call('results_spatial_plan',dict(self.args,candidate_ids=[self.records[0]['candidate_id']],policy=policy('ligand',requireGeometry=True)))

if __name__=='__main__':unittest.main()
