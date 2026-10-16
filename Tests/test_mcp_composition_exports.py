"""Exercise new MCP routes without running a scientific model."""
import base64
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

MCP=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/mcp'
sys.path.insert(0,str(MCP))
from iprotein_mcp import common,composition,exports,broker,plans,research
from server import MCPServer

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-contract-')
        self.root=Path(self.temp.name).resolve()
        self.env=patch.dict(os.environ,{'IPROTEINSTUDIO_TEST_SUPPORT_ROOT':str(self.root),'IPROTEINSTUDIO_AGENT_ROOT':str(self.root/'agent')})
        self.env.start()
        os.environ.pop('NANOHUNTER_ROOT',None)
        self.inputs=self.root/'projects/demo/inputs';self.inputs.mkdir(parents=True)
        self.template=self.inputs/'target.yaml';self.template.write_text('sequences: []\n')
        self.runner=self.root/'nanohunter_run.sh'
        self.runner.write_text('''#!/usr/bin/python3
import sys,csv
from pathlib import Path
a=sys.argv[1:];o=Path(a[a.index('--out-root')+1])/a[a.index('--run-name')+1];o.mkdir(parents=True,exist_ok=True)
with (o/'executions.txt').open('a') as h:h.write('run\\n')
with (o/'summary_all_runs.csv').open('w') as h:h.write('run,cycle,binder_sequence\\n1,1,ACDEFG\\n')
if a[a.index('--predictor')+1]=='intellifold' and (o.parent/'fail-second').exists():raise SystemExit(17)
print('Completed fixture',flush=True)
''');self.runner.chmod(0o755)
    def tearDown(self):
        self.env.stop();self.temp.cleanup()
    def arguments(self):
        return {'project':'demo','run_name':'batch','common':{'template_path':str(self.template),'arguments':['--workflow','protein','--sequence-designer','solublempnn','--num-opt-cycles','1','--iptm-threshold','0.7','--predictor-seed','42']},'engines':[{'predictor':'boltz'},{'predictor':'intellifold','model':'v2-flash'}],'trajectories_per_engine':2}
    def test_batch_executes_and_checkpoint_does_not_repeat_children(self):
        plan=composition.iterative_batch_plan(self.arguments())
        job=broker.start_job(plan['id'],plan['sha256'])
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            state=broker.load_state(job['id'])
            if state['status'] in broker.TERMINAL and not common.process_alive(state.get('pid')):break
            time.sleep(.1)
        self.assertEqual(state['status'],'completed',state)
        self.assertEqual(state['output_root'],plan['normalized_request']['output'])
        children=plan['normalized_request']['child_outputs']
        for child in children:self.assertEqual((Path(child)/'executions.txt').read_text(),'run\n')
        with patch.object(broker,'_execute_iterative',side_effect=AssertionError('repeated child')):
            self.assertEqual(broker._execute_iterative_batch(job['id'],plan),0)
        (Path(children[0])/'summary_all_runs.csv').write_text('changed')
        with self.assertRaisesRegex(common.StudioError,'artifacts changed'):
            broker._execute_iterative_batch(job['id'],plan)
    def terminal(self, job_id):
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            state=broker.load_state(job_id)
            if state['status'] in broker.TERMINAL and not common.process_alive(state.get('pid')): return state
            time.sleep(.1)
        self.fail(str(state))
    def test_failed_batch_resumes_only_incomplete_child(self):
        marker=self.root/'projects/demo/fail-second';marker.write_text('fail')
        plan=composition.iterative_batch_plan(self.arguments());job=broker.start_job(plan['id'],plan['sha256'])
        self.assertEqual(self.terminal(job['id'])['status'],'failed')
        marker.unlink();broker.resume_job(job['id'])
        self.assertEqual(self.terminal(job['id'])['status'],'completed')
        children=plan['normalized_request']['child_outputs']
        self.assertEqual((Path(children[0])/'executions.txt').read_text(),'run\n')
        self.assertEqual((Path(children[1])/'executions.txt').read_text(),'run\nrun\n')

    def test_batch_scaffold_budget_and_checker_validation(self):
        value=self.arguments();value['common']['arguments'][1]='nanobody';value['common'].pop('template_path')
        value['scaffolds']=[{'id':'A','template_path':str(self.template),'trajectories':1,'cdr_ranges':'CDR1:2-4,CDR2:6-8,CDR3:10-12'}]
        with self.assertRaisesRegex(common.StudioError,'sum'):composition.iterative_batch_plan(value)
        value['scaffolds'][0]['trajectories']=2
        plan=composition.iterative_batch_plan(value)
        for child in plan['normalized_request']['children']:
            self.assertEqual(child['trajectories'],2)
            self.assertIn('CDR1:2-4,CDR2:6-8,CDR3:10-12',child['plan']['normalized_request']['arguments'])
        value=self.arguments();value['common']['arguments']+=['--post-predictor','boltz']
        with self.assertRaisesRegex(common.StudioError,'No independent checker'):composition.iterative_batch_plan(value)
    def test_recipe_binds_digest_and_uses_existing_planner(self):
        recipe={'schema_version':2,'route':'protein_hunter_batch','parameters':self.arguments()}
        plan=composition.recipe_plan(recipe)
        self.assertEqual(plan['normalized_request']['pipeline_recipe']['recipe_sha256'],common.canonical_digest(recipe))
        plans.load_plan(plan['id'],plan['sha256'])
        recipe['parameters']['unknown']=True
        with self.assertRaises(common.StudioError):composition.recipe_plan(recipe)
        self.assertIsNone(composition.PLAN_CONTEXT.get())
    def campaign(self,count=2):
        root=self.root/'projects/demo/results';root.mkdir()
        (root/'studio_run.json').write_text(json.dumps({'arguments':['--predictor','boltz']}))
        pdb=root/'design.pdb';pdb.write_text('ATOM fixture\n')
        rows=['run,cycle,stage,predictor,structure_path,ipsae_min,is_hit,binder_sequence']
        rows += [f'1,{i},post,intellifold,design.pdb,0.7,{str(i==1).lower()},ACDEFG' for i in range(count)]
        (root/'comparison_scores_long.csv').write_text('\n'.join(rows)+'\n')
        return root
    def test_export_pagination_archive_lineage_and_integrity(self):
        root=self.campaign()
        page=MCPServer('run').tool_call('candidates_list',{'run_id':'demo/results','limit':1});second=exports.candidates_list('demo/results',1,page['next_cursor'])
        self.assertIsNone(second['next_cursor']);self.assertEqual(page['total_count'],2)
        rows=page['candidates']+second['candidates'];self.assertEqual(sum(r['is_hit'] is True for r in rows),1)
        compared=MCPServer('read').tool_call('candidates_compare',{'run_ids':['demo/results'],'metric':'ipsae_min','threshold':0.75})
        self.assertEqual(compared['summaries'][0]['with_single_metric'],2)
        self.assertEqual(compared['summaries'][0]['passed'],0)
        exported=MCPServer('run').tool_call('candidate_export',{'run_id':'demo/results','candidate_ids':[r['candidate_id'] for r in rows],'snapshot_sha256':page['snapshot_sha256']})
        resource=MCPServer('read').dispatch({'method':'resources/read','params':{'uri':exported['uri']}})
        self.assertEqual(json.loads(resource['contents'][0]['text'])['export_sha256'],exported['export_sha256'])
        data=bytearray();offset=0
        while offset is not None:
            chunk=exports.export_read(exported['export_sha256'],offset,200)
            part=base64.b64decode(chunk['data_base64']);self.assertEqual(hashlib.sha256(part).hexdigest(),chunk['chunk_sha256']);data.extend(part);offset=chunk['next_offset']
        self.assertEqual(hashlib.sha256(data).hexdigest(),exported['export_sha256'])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            manifest=json.loads(z.read('manifest.json'));self.assertEqual(len(manifest['candidates']),2)
            self.assertIn(b'ACDEFG',z.read('sequences.fasta'))
            for name,item in manifest['files'].items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),item['sha256'])
        (root/'design.pdb').write_text('Changed coordinates\n')
        with self.assertRaisesRegex(common.StudioError,'Results changed'):exports.candidates_list('demo/results',1,page['next_cursor'])
        with self.assertRaisesRegex(common.StudioError,'Results changed'):exports.candidate_export('demo/results',[rows[0]['candidate_id']],page['snapshot_sha256'])
    def test_complete_scan_exceeds_old_thousand_row_cap(self):
        self.campaign(1005)
        self.assertEqual(exports.candidates_list('demo/results')['total_count'],1005)
    def test_profiles_resources_and_prompt(self):
        server=MCPServer('read');self.assertIn('routes',server.tool_call('pipeline_catalog',{}))
        for name in ['candidate_export','pipeline_recipe_plan','rcsb_import_structure','iterative_batch_plan']:
            with self.assertRaisesRegex(common.StudioError,'not available'):server.tool_call(name,{})
        result=server.dispatch({'method':'resources/read','params':{'uri':'iprotein://skills/studio'}})
        self.assertIn('workflow_guide',result['contents'][0]['text'])
        self.assertTrue(server.dispatch({'method':'prompts/get','params':{'name':'studio-workflow','arguments':{'objective':'Compare supported models'}}})['messages'])
    def test_research_fails_closed_without_runtime_and_unknown_tools(self):
        self.assertFalse(research.status()['installed'])
        with self.assertRaisesRegex(common.StudioError,'not installed'):research.tools_list()
        with self.assertRaises(common.StudioError):research.query('arbitrary_shell',{})
        with self.assertRaises(common.StudioError):research.import_structure('4HHB','../2')
    def test_native_ligand_verification_is_frozen_and_executed(self):
        from iprotein_mcp import ligand_screening
        preparation=self.root/'agent-verification';(preparation/'runtime').mkdir(parents=True)
        config=preparation/'config.json';config.write_text('{}')
        checker=preparation/'runtime/check.py';checker.write_text('# frozen checker')
        options={'enabled':True,'engine':'psichic','topK':2,'predictor':'boltz'}
        request={'project':'demo','run_name':'ligand','template_path':str(self.template),
            'arguments':self.arguments()['common']['arguments']+['--predictor','boltz','--num-runs','1'],
            'ligand_verification':options}
        prepared={'directory':str(preparation),'step':{'command':['fake-checker'],'cwd':str(preparation/'runtime'),'stage':'nesso-verification'}}
        with patch.object(ligand_screening,'template_smiles',return_value='CCO'), patch.object(ligand_screening,'frozen_preparation',return_value=(prepared,[checker,config])) as freeze:
            plan=plans.iterative_plan(request)
            self.assertEqual(freeze.call_args.args[-2:],(options,'CCO'))
        calls=[]
        with patch.object(broker,'_update'),patch.object(broker,'_run_logged',side_effect=lambda *a: calls.append(a) or 0):
            self.assertEqual(broker._execute_iterative('fixture',plan),0)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][1],['fake-checker'])
        self.assertTrue((Path(plan['normalized_request']['campaign'])/'nesso_verification/config.json').is_file())
        config.write_text('changed')
        with self.assertRaises(common.StudioError):plans.load_plan(plan['id'],plan['sha256'])

    def test_rfd3_native_verification_staged_before_preparation(self):
        from iprotein_mcp import ligand_screening
        preparation=self.root/'verification';(preparation/'runtime').mkdir(parents=True)
        (preparation/'config.json').write_text('{}')
        scripts=self.root/'rfd3_scripts';scripts.mkdir();(scripts/'prepare_campaign.py').write_text('# fixture')
        runner=self.root/'rfd3_overlay/scripts/run_rfd3_nise_campaign.py';runner.parent.mkdir(parents=True);runner.write_text('# fixture')
        ligand=self.inputs/'ligand.cif';ligand.write_text('data_fixture\n')
        options={'enabled':True,'engine':'psichic','topK':1,'predictor':'boltz'}
        prepared={'directory':str(preparation),'step':{'command':['fixture'],'cwd':str(preparation/'runtime'),'stage':'nesso-verification'}}
        with patch.object(ligand_screening,'frozen_preparation',return_value=(prepared,[preparation/'config.json'])):
            plan=plans.rfd3_plan({'project':'demo','run_name':'rfd3','request':{'target_kind':'small_molecule','smiles':'CCO','ligand_source':'structure_file','ligand_structure':str(ligand),'num_backbones':1,'nesso':options}},'deNovo')
        self.assertEqual(plan['normalized_request']['request']['nesso'],options)
        campaign=Path(plan['normalized_request']['campaign'])
        def run(job_id,command,cwd,env):
            self.assertTrue((campaign/'nesso_verification/runtime').is_dir())
            self.assertTrue((campaign/'nesso_verification/config.json').is_file())
            config=campaign/'config/campaign.json';config.write_text('{}')
            log=broker.state_path(job_id).parent/'pipeline.log';log.parent.mkdir(parents=True,exist_ok=True);log.write_text('PREPOK|'+str(config)+'\n')
            return 0
        with patch.object(broker,'_update'),patch.object(broker,'_run_logged',side_effect=run) as invoke:
            self.assertEqual(broker._execute_rfd3('job-fixture',plan),0)
            self.assertEqual(invoke.call_count,2)
        Path(plan['normalized_request']['request']['ligand_structure']).write_text('changed')
        with self.assertRaises(common.StudioError):plans.load_plan(plan['id'],plan['sha256'])

    def test_progress_cannot_erase_cancel_intent_or_reopen_terminal_job(self):
        path=broker.state_path('job-state-race');path.parent.mkdir(parents=True)
        common.atomic_json(path,{'status':'running','stage':'starting'})
        common.atomic_json(path.parent/'cancel.json',{'requested_at':common.utc_now()})
        broker._update('job-state-race',status='running',stage='prediction')
        self.assertEqual(broker.load_state('job-state-race')['status'],'stopping')
        broker._update('job-state-race',status='cancelled',stage='cancelled')
        broker._update('job-state-race',status='stopping',stage='stopping')
        self.assertEqual(broker.load_state('job-state-race')['status'],'cancelled')

    def test_chunk_bounds_and_nonfinite_numbers(self):
        with self.assertRaises(common.StudioError):exports.export_read('a'*64,-1)
        with self.assertRaises(common.StudioError):common.validate_schema(float('nan'),{'type':'number'})
        with self.assertRaises(common.StudioError):common.validate_schema('long',{'type':'string','maxLength':2})

if __name__=='__main__':unittest.main()
