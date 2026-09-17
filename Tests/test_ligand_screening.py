"""Shared campaign screening contracts; deterministic fake models, no inference."""
import csv
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import importlib.util
import yaml
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS / 'nise'))
import ligand_screening as screen
from nesso_contract import SCALARS, installation
from runtime import atomic


class Client:
    loads = calls = closes = 0
    fail_at = None
    invalid = False
    def __init__(self, *args):
        type(self).loads += 1
    def score(self, sequence, smiles, directory):
        cls = type(self)
        if cls.calls == cls.fail_at:
            raise RuntimeError('injected interruption')
        cls.calls += 1
        # C ranks above A despite its lower P(bind). G has invalid placement.
        p, entropy = {'A': (.99, .9), 'C': (.8, .2), 'G': (.999, 0)}[sequence[0]]
        values = dict.fromkeys(SCALARS, 0.0)
        values.update(affinity_probability_binary=p, entropy_crop_pl=0 if cls.invalid else entropy, entropy_pl=.95)
        atomic(directory / 'affinity.json', values)
        return dict(scores=values)
    def close(self):
        type(self).closes += 1


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'campaign/nesso_verification'
        self.output.mkdir(parents=True)
        base = installation(self.root); base.mkdir(parents=True)
        (base / 'receipt.json').write_text('test installation')
        self.source = self.root / 'sequences.csv'
        self.source.write_text('design,seq_index,sequence\ndesign_0001,1,ACDE\ndesign_0001,2,CCDE\ndesign_0002,1,GCDE\n')
        self.runner = self.root / 'runner.py'; self.runner.write_text('# fake adapter')
        self.config = self.output / 'config.json'
        self.cfg = dict(version=1, root=str(self.root), output=str(self.output), workflow='rfdiffusion3',
                        source=str(self.source), options=dict(enabled=True, topK=2, predictor='intellifold', intellifoldModel='v2'),
                        smiles='CCO', scripts=str(SCRIPTS), predictor_runner=str(self.runner))
        atomic(self.config, self.cfg)
        Client.loads = Client.calls = Client.closes = 0; Client.fail_at = None; Client.invalid = False
        self.fold_calls = []; self.partial = False
    def tearDown(self):
        self.temp.cleanup()
    def predict(self, command, **kwargs):
        inputs = Path(command[command.index('--inputs')+1])
        output = Path(command[command.index('--output')+1])
        predictor = command[command.index('--predictors')+1]
        self.assertEqual(command[command.index('--intellifold-model')+1], 'v2')
        names = sorted(path.stem for path in inputs.glob('*.yaml'))
        self.fold_calls.append(names)
        rows = []
        for index, name in enumerate(names):
            payload = yaml.safe_load((inputs / (name+'.yaml')).read_text())
            spec = importlib.util.spec_from_file_location('actual_predictors', ROOT / 'Sources/iProteinStudio/Resources/rfd3_overlay/scripts/run_predictors.py')
            adapters = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapters)
            self.assertFalse(adapters.yaml_uses_real_msa(inputs / (name+'.yaml')))
            self.assertEqual(payload['sequences'][0]['protein']['msa'], 'empty')
            self.assertEqual(payload['sequences'][1]['ligand']['smiles'], self.cfg['smiles'])
            if self.partial and index:
                rows.append(dict(design=name, predictor=predictor, exit_code=1)); continue
            directory = output / predictor / name; directory.mkdir(parents=True, exist_ok=True)
            structure = directory / 'model.cif'; structure.write_text('data_fixture\n')
            confidence = directory / 'confidence.json'; atomic(confidence, dict(iptm=.6))
            rows.append(dict(design=name, predictor=predictor, exit_code=0, structure=str(structure), confidence_json=str(confidence), iptm=.6))
        fields = sorted({key for row in rows for key in row})
        with (output / 'prediction_metrics.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        return SimpleNamespace(returncode=int(self.partial))
    def run_screen(self):
        return screen.run(self.config, client_class=Client, predictor_run=self.predict)
    def test_cropped_ranking_global_shortlist_and_resident_lifetime(self):
        results = self.run_screen()
        self.assertEqual([r['candidate'] for r in results], ['design_0001_2', 'design_0001_1'])
        self.assertEqual(results[0]['nesso']['screening_score'], 1.6)
        self.assertEqual(results[0]['origin'], dict(backbone='design_0001', derivative='2'))
        self.assertEqual(results[0]['structure_scores'], dict(iptm=.6))
        self.assertEqual((Client.loads, Client.calls, Client.closes), (1,3,1))
        report = list(csv.DictReader((self.output / 'nesso_screening.csv').open()))
        self.assertEqual(report[2]['eligible'], 'False')
        self.assertEqual(report[2]['selected'], 'False')
    def test_completed_resume_does_no_inference_and_audits_artifacts(self):
        first = self.run_screen(); self.assertEqual(self.run_screen(), first)
        self.assertEqual(Client.calls, 3); self.assertEqual(len(self.fold_calls), 1)
        (self.output / first[0]['structure']).write_text('changed')
        with self.assertRaisesRegex(RuntimeError, 'missing or changed'): self.run_screen()
    def test_interrupted_screen_resumes_at_next_candidate(self):
        Client.fail_at = 1
        with self.assertRaisesRegex(RuntimeError, 'interruption'): self.run_screen()
        self.assertEqual(Client.closes, 1)
        Client.fail_at = None; self.run_screen()
        self.assertEqual(Client.calls, 3); self.assertEqual(Client.loads, 2)
    def test_partial_predictions_checkpoint_successes(self):
        self.partial = True
        with self.assertRaisesRegex(RuntimeError, 'incomplete'): self.run_screen()
        self.partial = False; results = self.run_screen()
        self.assertEqual(len(results), 2); self.assertEqual(Client.calls, 3)
        self.assertEqual(len(self.fold_calls[1]), 1)
    def test_changed_source_refuses_resume(self):
        self.run_screen(); self.source.write_text(self.source.read_text()+'design_3,1,ACDE\n')
        with self.assertRaisesRegex(RuntimeError, 'inputs changed'): self.run_screen()
    def test_all_invalid_saves_report_without_folding(self):
        Client.invalid = True
        with self.assertRaisesRegex(RuntimeError, 'every placement'): self.run_screen()
        self.assertTrue((self.output / 'nesso_screening.csv').is_file()); self.assertEqual(self.fold_calls, [])
    def test_shortlist_is_maximum_not_required_count(self):
        self.cfg['options']['topK'] = 20; atomic(self.config, self.cfg)
        self.assertEqual(len(self.run_screen()), 2)
    def test_ph_excludes_seeds_but_keeps_all_optimized_cycles(self):
        self.source.write_text('run,cycle,binder_sequence\nrun_001,cycle_00,XXXX\n1,1,ACDE\n1,2,CCDE\n')
        entries = screen.candidates(self.source, 'iterative')
        self.assertEqual(list(entries), ['run_001_cycle_01', 'run_001_cycle_02'])
        self.cfg['workflow']='iterative'; atomic(self.config,self.cfg)
        self.assertEqual(self.run_screen()[0]['candidate'], 'run_001_cycle_02')
    def test_rejects_duplicate_identity_and_masked_design(self):
        for content, error in [('design,seq_index,sequence\na,1,ACDE\na,1,CCDE\n','Duplicate'),
                               ('design,seq_index,sequence\na,1,XXXX\n','masked')]:
            self.source.write_text(content)
            with self.assertRaisesRegex(ValueError,error): screen.candidates(self.source,'rfdiffusion3')
    def test_stereochemical_smiles_survives_openfold_query_adapter(self):
        import subprocess
        self.cfg['smiles'] = r'F/C=C\F'; atomic(self.config, self.cfg)
        self.run_screen()
        query = next((self.output/'prediction_inputs').glob('*/*.yaml'))
        destination = self.root/'openfold.json'
        result = subprocess.run([sys.executable, str(SCRIPTS/'openfold_query_json.py'), str(query), 'ACDE', 'fixture', str(destination)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'false')
        ligand = json.loads(destination.read_text())['queries']['fixture']['chains'][1]
        self.assertEqual(ligand['smiles'], self.cfg['smiles'])

    def test_invalid_options_fail_before_worker(self):
        for key, value in [('topK',0),('topK',True),('predictor','alphafold3'),('intellifoldModel','unknown')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                screen.options({**self.cfg['options'],key:value})
        self.assertEqual(Client.loads, 0)


class PreflightTests(unittest.TestCase):
    def test_freezes_dependencies_checks_full_checkpoint_and_refuses_changed_resume(self):
        import shutil
        sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp'))
        from iprotein_mcp.ligand_screening import prepare
        from iprotein_mcp.common import StudioError
        import nesso_contract
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); out = root / 'campaign'
            shutil.copytree(SCRIPTS / 'nise', root / 'scripts/nise', ignore=shutil.ignore_patterns('__pycache__'))
            adapters = root / 'rfd3_overlay/scripts'; adapters.mkdir(parents=True)
            (adapters / 'run_predictors.py').write_text('# fixture adapter')
            asset = root / 'model'; asset.write_text('fixture checkpoint')
            for relative in ['models/intellifold/intellifold_v2.pt', 'models/intellifold/ccd_v2.pkl', 'venvs/NanoHunter_intellifold/bin/python']:
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('fixture')
            opts = dict(enabled=True, topK=2, predictor='intellifold', intellifoldModel='v2')
            with patch.object(nesso_contract, 'validate_installation'), patch.object(nesso_contract, 'installation_files', return_value=[asset]):
                with self.assertRaisesRegex(StudioError,'intellifold_full'):
                    prepare(root,out,'iterative',opts,'CCO',detected={'intellifold':{'state':'ok'}})
                engines={key: {'state':'ok'} for key in ['intellifold','intellifold_full']}
                first, assets = prepare(root,out,'iterative',opts,'CCO',detected=engines)
                self.assertEqual(first['stage'], 'nesso-verification')
                self.assertTrue(any(p.name=='config.json' for p in assets))
                # Python bytecode created during a run cannot invalidate a snapshot.
                cache=out/'nesso_verification/runtime/scripts/nise/__pycache__';cache.mkdir(exist_ok=True)
                (cache/'test.pyc').write_bytes(b'generated')
                second, _ = prepare(root,out,'iterative',opts,'CCO',detected=engines)
                self.assertEqual(first, second)
                asset.write_text('changed checkpoint')
                with self.assertRaisesRegex(StudioError,'dependencies changed'):
                    prepare(root,out,'iterative',opts,'CCO',detected=engines)

    def test_rfd3_route_and_resume_reaudits_screen(self):
        sys.path.insert(0, str(ROOT/'Sources/iProteinStudio/Resources/rfd3_overlay/scripts'))
        spec=importlib.util.spec_from_file_location('rfd3_campaign', ROOT/'Sources/iProteinStudio/Resources/rfd3_overlay/scripts/run_rfd3_nise_campaign.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve(); cfg=root/'campaign.json'
            design=root/'design.yaml';design.write_text('fixture')
            smiles=root/'ligand.smi';smiles.write_text('CCO')
            atomic(cfg, dict(campaign_dir=str(root),design_yaml=str(design),smiles_file=str(smiles),nesso=dict(enabled=True)))
            atomic(root/'campaign_progress.json',dict(completed_stages=['validate','fixtures','backbones','mpnn','nesso']))
            with ExitStack() as stack:
                stack.enter_context(patch.object(sys,'argv',['runner','--config',str(cfg),'--resume']))
                calls = [stack.enter_context(patch.object(module, name)) for name in
                         ['stage_validate', 'stage_fixtures', 'stage_backbones', 'stage_mpnn', 'stage_nesso']]
                module.main()
                self.assertTrue(all(call.call_count == 1 for call in calls))
            saved=json.loads((root/'campaign_progress.json').read_text())
            self.assertEqual(saved['completed_stages'].count('nesso'),1)
            with patch.object(sys,'argv',['runner','--config',str(cfg),'--stage','predict-holo']), self.assertRaisesRegex(SystemExit,'verification route'):
                module.main()


if __name__ == '__main__': unittest.main()
