"""Real Hunter YAML writer and Full input parser; no learned inference."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PIPE = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0, str(PIPE / 'scripts'))
import esmfold2_predict as adapter
from esmfold2_cdr import KEY, make_contract, positions
import hunter_stages
import yaml


class CDRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with (PIPE / 'examples/nanobody_scaffolds/catalog.tsv').open() as f:
            self.scaffold = next(csv.DictReader(f, delimiter='\t'))['sequence']
        self.contract = make_contract(self.scaffold)
        self.masked = ''.join('X' if i in positions(self.contract) else a for i, a in enumerate(self.scaffold, 1))
        self.data = dict(version=1, sequences=[dict(protein=dict(id='A', sequence=self.masked, msa='empty')),
                                              dict(protein=dict(id='B', sequence='ACDEFGHIK', msa='empty'))],
                         **{KEY: self.contract})
        self.path = self.root / 'input.yaml'

    def read(self, model='full'):
        self.path.write_text(yaml.safe_dump(self.data))
        return adapter.read_input(self.path, model)

    def test_full_preserves_native_x_and_rejects_fast(self):
        self.assertEqual(self.read()[0][0]['sequence'], self.masked)
        with self.assertRaisesRegex(ValueError, 'only with ESMFold2 Full'):
            self.read('fast')

    def test_missing_contract_and_framework_or_target_x_rejected(self):
        self.data.pop(KEY)
        with self.assertRaisesRegex(ValueError, 'X-token'): self.read()
        self.data[KEY] = self.contract
        self.data['sequences'][0]['protein']['sequence'] = 'X' + self.masked[1:]
        with self.assertRaisesRegex(ValueError, 'framework'): self.read()
        self.data['sequences'][0]['protein']['sequence'] = self.masked
        self.data['sequences'][1]['protein']['sequence'] = 'ACXEFGHIK'
        with self.assertRaisesRegex(ValueError, 'X-token'): self.read()

    def test_masked_msa_required_and_missing_msa_fails(self):
        msa = self.root / 'scaffold.a3m'
        self.data['sequences'][0]['protein']['msa'] = str(msa)
        with self.assertRaisesRegex(ValueError, 'missing'): self.read()
        msa.write_text('>q\n' + self.masked + '\n>h\n' + self.scaffold + '\n')
        with self.assertRaisesRegex(ValueError, 'mask every'): self.read()
        msa.write_text('>q\n' + self.masked + '\n>h\n' + self.masked.replace('X', '-') + '\n')
        self.assertIn(str(msa.resolve()), self.read()[1])

    def test_actual_hunter_writer_scopes_permission_to_cycle_zero(self):
        source = (PIPE / 'nanohunter_run.sh').read_text()
        start = source.index('make_yaml_with_binder_sequence()')
        end = source.index('\nPY\n}', start) + len('\nPY\n}')
        shell = self.root / 'writer.sh'
        shell.write_text(source[start:end] + '\nmake_yaml_with_binder_sequence "$@"\n')
        template = self.root / 'template.yaml'
        template.write_text('version: 1\nsequences:\n- protein:\n    id: A\n    sequence: ' + self.scaffold + '\n    msa: empty\n- protein:\n    id: B\n    sequence: ACDEFGHIK\n    msa: empty\n')
        env = dict(os.environ, PIPELINE_CODE_ROOT=str(PIPE), WORKFLOW='nanobody',
                   NANOBODY_SEED_CDR_RANGES='auto', NANOBODY_SEED_CDRS='CDR1 CDR2 CDR3',
                   TARGET_EPITOPE_RESIDUES='', BOLTZ_CONTACT_DISTANCE='6', BOLTZ_CONTACT_FORCE='0',
                   BOLTZ_CONTACT_MODE='auto', REFINEMENT_EPITOPE_GUIDANCE='auto')
        command = ['bash', str(shell), str(template), str(self.path), self.masked, '', 'esmfold2-full-mlx', '', 'design', '0']
        subprocess.run(command, env=env, check=True, capture_output=True)
        chains, _ = adapter.read_input(self.path, 'full')
        self.assertEqual(chains[0]['sequence'], self.masked)
        document = yaml.safe_load(self.path.read_text())
        self.assertEqual(document[KEY]['scaffold'], self.scaffold)
        command[-1] = '1'
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cycle 00', result.stderr)

    def test_starting_engine_routes(self):
        args = ['--initialization-method', 'hallucination', '--initialization-predictor', 'esmfold2-full-mlx', '--workflow', 'nanobody']
        self.assertEqual(hunter_stages.validate(args)[1], 'esmfold2-full-mlx')
        for invalid in ('protein', 'monomer'):
            with self.assertRaises(ValueError): hunter_stages.validate(args[:-1] + [invalid])


if __name__ == '__main__': unittest.main()
