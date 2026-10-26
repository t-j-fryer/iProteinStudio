"""Real immutable desktop plan for file-only preparation; no engine mocks."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import subprocess
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0, str(PIPELINE / 'mcp'))
from iprotein_mcp.desktop import desktop_plan
from iprotein_mcp.plans import load_plan
from iprotein_mcp.common import StudioError
from iprotein_mcp import broker
from server import MCPServer


class Bridge(unittest.TestCase):
    def test_public_cli_mcp_preparation_and_result_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'projects/demo').mkdir(parents=True)
            shutil.copytree(PIPELINE / 'scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(PIPELINE / 'mcp', root / 'mcp', ignore=shutil.ignore_patterns('__pycache__'))
            with patch.dict(os.environ, NANOHUNTER_ROOT=str(root), IPROTEINSTUDIO_AGENT_ROOT=str(root / 'agent')):
                read, run = MCPServer('read'), MCPServer('run')
                self.assertEqual(len(read.tool_call('motif_beta_catalog', {})['cases']), 41)
                self.assertEqual(read.tool_call('workflow_guide', {'workflow':'motif_beta'})['tool'], 'motif_beta_plan')
                evidence = read.dispatch({'method':'resources/read','params':{'uri':'iprotein://skills/studio/evidence'}})
                self.assertTrue(evidence['contents'][0]['text'])
                recipe = run.tool_call('pipeline_recipe_plan', {'recipe':{'schema_version':2,'route':'motif_beta',
                    'parameters':{'project':'demo','run_name':'recipe','request':{'stage':'prepare'}}}})
                self.assertEqual(recipe['normalized_request']['pipeline_recipe']['recipe']['route'], 'motif_beta')
                request = dict(project='demo', run_name='public', request={'stage':'prepare'})
                with self.assertRaises(StudioError): read.tool_call('motif_beta_plan', request)
                for changes in [{'roots':6}, {'engine':'protenix-v2','stage':'cycles'}, {'unexpected':True}]:
                    with self.assertRaises(StudioError): run.tool_call('motif_beta_plan', request | {'request':changes})
                path = root / 'request.json'; path.write_text(json.dumps(request))
                cli = subprocess.run([sys.executable, '-B', str(PIPELINE/'mcp/studioctl.py'), 'plan-motif-beta', str(path)], capture_output=True, text=True)
                self.assertEqual(cli.returncode, 0, cli.stderr)
                plan = json.loads(cli.stdout)
                self.assertEqual(plan['kind'], 'desktop_motif_beta')
                with self.assertRaises(StudioError): run.tool_call('motif_beta_plan', request)
                job = broker.start_job(plan['id'], plan['sha256'])
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    state = broker.load_state(job['id'])
                    if state['status'] in broker.TERMINAL: break
                    time.sleep(.05)
                self.assertEqual(state['status'], 'completed', state)
                output = Path(plan['normalized_request']['output'])
                self.assertFalse(json.loads((output/'status.json').read_text())['inference'])
                run_id = 'demo/motif_beta/public'
                self.assertIn(run_id, [r['id'] for r in read.tool_call('runs_list', {'project':'demo'})['runs']])
                self.assertEqual(read.tool_call('results_overview', {'run_id':run_id})['groups'], [])
                # Synthetic archive tests exact role attribution and path confinement, not science.
                (output/'guided.cif').write_text('fixture')
                (output/'checked.cif').write_text('fixture')
                candidates = [{'id':'root/laser-beam/1/candidate','root':'root','arm':'laser-beam',
                    'cycle':1,'parent':'root','structure':str(output/'guided.cif'),
                    'checked_structure':str(output/'checked.cif'),'metrics':{'guarded_pass':True}}]
                (output/'comparison_results.json').write_text(json.dumps({'candidates':candidates}))
                overview = read.tool_call('results_overview', {'run_id':run_id})
                artifacts = overview['groups'][0]['variants'][0]['artifacts']
                self.assertEqual([a['role'] for a in artifacts], ['proposal','untemplated_search_check'])
                self.assertTrue(all(a['is_hit'] is None for a in artifacts))
                rows = read.tool_call('results_query', {'run_id':run_id,'dataset':'comparison_results.json'})['rows']
                self.assertEqual(rows[0]['checked_structure'], 'checked.cif')

    def test_preparation_plan_is_content_bound_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scripts = root / 'scripts'; scripts.mkdir()
            shutil.copytree(PIPELINE / 'scripts/motif_beta', scripts / 'motif_beta', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(PIPELINE / 'scripts/motif_beta_cli.py', scripts / 'motif_beta_cli.py')
            output = root / 'projects/demo/motif_beta/one'; output.mkdir(parents=True)
            config = output / 'motif_beta_request.json'; config.write_text(json.dumps({'stage': 'prepare'}))
            with patch.dict(os.environ, NANOHUNTER_ROOT=str(root), IPROTEINSTUDIO_AGENT_ROOT=str(root / 'agent')):
                request = dict(project='demo', workflow='motif_beta', output=str(output))
                plan = desktop_plan(request)
                self.assertEqual(plan['normalized_request']['request']['roots'], 1)
                self.assertEqual(load_plan(plan['id'], plan['sha256'])['sha256'], plan['sha256'])
                self.assertTrue(any('M0040_13pk.pdb' in p['path'] for p in plan['provenance']))
                config.write_text(json.dumps({'stage': 'prepare', 'roots': 6}))
                with self.assertRaises(StudioError): desktop_plan(request)
                with self.assertRaises(StudioError): load_plan(plan['id'], plan['sha256'])


if __name__ == '__main__': unittest.main()
