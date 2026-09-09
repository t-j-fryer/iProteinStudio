#!/usr/bin/env python3
"""Execute Predict template conversion/routing with synthetic structures, no models."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import prediction_templates as templates
import prepare_intellifold_template as intelli
import protenix_predict as protenix
spec = importlib.util.spec_from_file_location('predict_batch', ROOT / 'Sources/iProteinStudio/Resources/rfd3/predict_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)
SEQ = 'ACDEFGHIKLMN'


class Templates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='predict-template-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'synthetic.pdb'
        residues = 'ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN'.split()
        lines = []
        serial = 0
        for i, residue in enumerate(residues, 1):
            for atom, dx, element in [('N', 0, 'N'), ('CA', 1.4, 'C'), ('C', 2.8, 'C'), ('O', 3.1, 'O')]:
                serial += 1
                lines.append(f'ATOM  {serial:5d} {atom:^4s} {residue} X{i:4d}    {i*3.8+dx:8.3f}{0.:8.3f}{0.:8.3f}{1.:6.2f}{50.:6.2f}          {element:>2s}\n')
        self.source.write_text(''.join(lines) + 'TER\nEND\n')
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.cfg = {'predictors': ['boltz', 'intellifold', 'protenix-v2'],
                    'intellifold_model': 'v2-flash',
                    'template': {'path': str(self.source), 'chains': ['A'], 'mode': 'guide'},
                    'jobs': [{'name': name, 'chains': [{'id': 'A', 'kind': 'protein', 'sequence': SEQ, 'msa': 'empty'}]} for name in ['one', 'two']]}
        self.write_inputs()

    def write_inputs(self):
        for job in self.cfg['jobs']:
            (self.inputs / (job['name'] + '.yaml')).write_text(batch.job_yaml(job, {}, False))

    def test_contract_rejections(self):
        templates.validate(self.cfg)
        for change in [{'chains': []}, {'chains': ['B']}, {'chains': ['A', 'A']}, {'mode': 'strong'}, {'path': str(self.root / 'absent.pdb')}]:
            bad = copy.deepcopy(self.cfg)
            bad['template'].update(change)
            with self.assertRaises(ValueError): templates.validate(bad)
        bad = copy.deepcopy(self.cfg)
        bad['predictors'] = ['openfold-3-mlx']
        with self.assertRaisesRegex(ValueError, 'supports'): templates.validate(bad)
        bad['predictors'] = ['boltz']
        bad['jobs'][0]['chains'].append({'id': 'B', 'kind': 'protein', 'sequence': SEQ})
        with self.assertRaisesRegex(ValueError, 'Identical'): templates.validate(bad)

    def test_all_engine_preparation_and_receipts(self):
        for engine in self.cfg['predictors']:
            out = self.root / engine
            templates.prepare(self.cfg, engine, self.inputs, out)
            before = (out / 'completed.json').read_bytes()
            templates.prepare(self.cfg, engine, self.inputs, out)
            self.assertEqual(before, (out / 'completed.json').read_bytes())
            document = yaml.safe_load((out / 'inputs/one.yaml').read_text())
            if engine == 'boltz':
                self.assertEqual(document['templates'][0]['chain_id'], ['A'])
                self.assertIn('_entity_poly_seq', Path(document['templates'][0]['cif']).read_text())
            elif engine == 'intellifold':
                protein = document['sequences'][0]['protein']
                self.assertIn(SEQ, Path(protein['template']).read_text())
                self.assertEqual(Path(protein['msa']).read_text(), '>query\n' + SEQ + '\n')
                manifest = json.loads((out / 'intellifold_manifest.json').read_text())
                self.assertEqual(len(manifest['mappings']), 2)
                self.assertEqual(manifest['binder_template'], 'selected')
            else:
                self.assertEqual(document['target_template']['scope'], 'prediction')
                converted, _, _ = protenix.convert_yaml(out / 'inputs/one.yaml', template_capable=True)
                sidecar = Path(converted['sequences'][0]['proteinChain']['templatesPath'])
                self.assertEqual(len(json.loads(sidecar.read_text())[0]['queryIndices']), len(SEQ))
            (out / 'inputs/one.yaml').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                templates.prepare(self.cfg, engine, self.inputs, out)

    def test_target_only_and_manual_msa(self):
        msa = self.root / 'manual.a3m'
        msa.write_text('>query\n' + SEQ + '\n>homologue\n' + SEQ + '\n')
        for job in self.cfg['jobs']:
            job['chains'] = [{'id': 'A', 'kind': 'protein', 'sequence': 'GGGGGSSSSS', 'msa': 'empty'},
                             {'id': 'B', 'kind': 'protein', 'sequence': SEQ, 'msa': str(msa)}]
        self.cfg['template']['chains'] = ['B']
        self.write_inputs()
        self.assertEqual(list(intelli.query_chains(self.inputs / 'one.yaml')), ['B'])
        out = self.root / 'intelli'
        templates.prepare(self.cfg, 'intellifold', self.inputs, out)
        proteins = [entry['protein'] for entry in yaml.safe_load((out / 'inputs/one.yaml').read_text())['sequences']]
        self.assertEqual(proteins[0]['template'], -1)
        self.assertEqual(proteins[0]['msa'], 'empty')
        self.assertEqual(Path(proteins[1]['msa']).read_bytes(), msa.read_bytes())
        msa.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            templates.prepare(self.cfg, 'intellifold', self.inputs, out)

    def test_protenix_design_guard_and_identical_copies(self):
        doc = {'target_template': {'path': str(self.source), 'sha256': templates.sha256(self.source), 'query_chains': ['A'], 'mode': 'guide'}}
        proteins = {'A': {'sequence': SEQ}, 'B': {'sequence': 'GGGGGSSSSS'}}
        with self.assertRaisesRegex(SystemExit, 'exclude binder'):
            protenix.apply_target_template(doc, self.inputs / 'one.yaml', proteins, True)
        doc['target_template']['scope'] = 'prediction'
        protenix.apply_target_template(doc, self.inputs / 'one.yaml', proteins, True)
        self.assertEqual(json.loads(Path(proteins['B']['templatesPath']).read_text()), [])
        doc['target_template']['query_chains'] = ['A', 'B']
        proteins['B']['sequence'] = SEQ
        protenix.apply_target_template(doc, self.inputs / 'one.yaml', proteins, True)
        self.assertEqual(proteins['A']['templatesPath'], proteins['B']['templatesPath'])

    def test_batch_command_keeps_multiple_inputs_and_local_manifest(self):
        out = self.root / 'prepared'
        templates.prepare(self.cfg, 'intellifold', self.inputs, out)
        envkey = 'IPROTEINSTUDIO_INTELLIFOLD_TEMPLATE_MANIFEST'
        for guided in [True, False]:
            cfg = self.cfg if guided else {}
            with patch.object(batch.subprocess, 'Popen') as popen:
                _, handle = batch.run_directory_batch('intellifold', list((out / 'inputs').glob('*.yaml')), self.root / 'fold', self.root, {envkey: 'stale'}, cfg, self.root / 'fold.log')
                handle.close()
                command = popen.call_args.args[0]
                self.assertEqual('--use_template' in command, guided)
                env = popen.call_args.kwargs['env']
                self.assertEqual(env.get(envkey), str(out / 'intellifold_manifest.json') if guided else None)
                self.assertEqual(len(list((self.root / 'fold/_inputs').glob('*.yaml'))), 2)

    def test_driver_entrypoint_freezes_template_before_inference(self):
        # Real driver and preparer subprocesses; inert engine records the routed YAMLs.
        (self.root / 'scripts').symlink_to(SCRIPTS, target_is_directory=True)
        runtime = self.root / 'venvs/NanoHunter_boltz/bin'
        runtime.mkdir(parents=True)
        (runtime / 'python').write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        (runtime / 'python').chmod(0o755)
        self.cfg.update(root=str(self.root), output=str(self.root / 'run'), predictors=['boltz'],
                        msa={'cache_dir': str(self.root / 'msa_cache'), 'index_roots': [], 'allow_server': False})
        config = self.root / 'config.json'
        config.write_text(json.dumps(self.cfg))
        seen = []
        class Completed:
            returncode = 0
            def poll(self): return 0
        def fake_engine(predictor, yamls, out_dir, *args):
            for path in yamls:
                document = yaml.safe_load(path.read_text())
                self.assertEqual(document['templates'][0]['chain_id'], ['A'])
                seen.append(path.stem)
                (out_dir / (path.stem + '.cif')).write_text('synthetic test output')
            return Completed(), (out_dir / 'engine.log').open('w')
        with patch.object(sys, 'argv', ['predict_batch.py', '--config', str(config)]), patch.object(batch, 'run_directory_batch', fake_engine), patch.object(batch, 'validate_geometry', return_value=0), patch.object(batch, 'annotate_boltz_ipsae', return_value=0), patch.object(batch.time, 'sleep'):
            batch.main()
            self.assertEqual(set(seen), {'one', 'two'})
            seen.clear()
            batch.main()
            self.assertEqual(seen, [])
            self.cfg.pop('template')
            config.write_text(json.dumps(self.cfg))
            with self.assertRaises(SystemExit): batch.main()

if __name__ == '__main__':
    unittest.main()
