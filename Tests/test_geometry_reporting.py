"""Execute reporting on distorted, valid, and unusable coordinate inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
SCRIPT = PIPELINE / 'scripts/validate_prediction_geometry.py'


def pdb(distance=2.28):
    atoms = [('CA', 1, 0.), ('C', 1, 1.), ('N', 2, 1.+distance), ('CA', 2, 3.8)]
    return ''.join(f'ATOM  {i:5d} {name:^4s} ALA A{residue:4d}    {x:8.3f}{0.:8.3f}{0.:8.3f}{1.:6.2f}{75.:6.2f}           C\n'
                   for i, (name, residue, x) in enumerate(atoms, 1))


class GeometryReportingTests(unittest.TestCase):
    def invoke(self, text):
        temporary = tempfile.TemporaryDirectory(prefix='geometry test ')
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'model.pdb'
        path.write_text(text)
        before = path.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
        report = json.loads((path.parent / 'geometry_report.json').read_text())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(report['structures'][0]['sha256'], hashlib.sha256(before).hexdigest())
        return result, report, path

    def test_peptide_violation_is_recorded_and_succeeds(self):
        result, report, _ = self.invoke(pdb())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['policy'], 'record_only')
        self.assertEqual(report['violation_count'], 1)
        self.assertTrue(report['coordinate_input_usable'])
        violation = report['structures'][0]['violations'][0]
        self.assertEqual(violation['atoms'], 'C-N')
        self.assertAlmostEqual(violation['distance_angstrom'], 2.28)
        self.assertEqual(violation['residue_1'], '1')
        self.assertIn('GEOMETRY_WARNING', result.stdout)

    def test_valid_input_has_explicit_zero_violations(self):
        result, report, _ = self.invoke(pdb(1.33))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['violation_count'], 0)

    def test_nonfinite_coordinates_still_fail_with_report(self):
        result, report, _ = self.invoke(pdb().replace('   0.000', '     nan', 1))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report['coordinate_input_usable'])
        self.assertIn('non-finite', result.stderr)

    def test_empty_structure_still_fails_with_report(self):
        result, report, _ = self.invoke('END\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['error_count'], 1)

    def test_iterative_shell_function_records_without_polluting_result_stdout(self):
        _, _, path = self.invoke(pdb())
        source = (PIPELINE / 'nanohunter_run.sh').read_text()
        function = re.search(r'^record_prediction_geometry\(\) \{.*?^\}', source, re.M | re.S).group()
        normalized = path.parent / 'pred_min'; normalized.mkdir()
        (normalized / 'model_0.pdb').symlink_to(path)
        result = subprocess.run(['bash', '-euc', function + '\nPIPELINE_CODE_ROOT="$1"\nrecord_prediction_geometry "$2"',
                                 'test', str(PIPELINE), str(normalized)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        report = json.loads((normalized / 'geometry_report.json').read_text())
        self.assertEqual(report['structures'][0]['path'], 'model_0.pdb')
        self.assertEqual(report['violation_count'], 1)

    def test_boltz_wrapper_continues_after_reported_violation(self):
        _, _, path = self.invoke(pdb())
        spec = importlib.util.spec_from_file_location('boltz_geometry_test', SCRIPT.with_name('boltz_mps.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.validate_output(['predict', '--out_dir', str(path.parent)])

    def test_iterative_prediction_failure_is_not_masked_by_reporting(self):
        source = (PIPELINE / 'nanohunter_run.sh').read_text()
        function = re.search(r'^run_predictor_once\(\) \{.*?^\}', source, re.M | re.S).group()
        script = function + '\nBOLTZ_USE_POTENTIALS_DEFAULT=0\nrun_predict_boltz() { return 7; }\nrecord_prediction_geometry() { echo unexpected; }\nrun_predictor_once boltz input seq query output none design'
        result = subprocess.run(['bash', '-uc', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
