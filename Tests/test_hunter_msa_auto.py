"""Execute the runner's actual target-MSA extractor without launching inference."""
import subprocess
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh'


class TargetMSAPolicyTests(unittest.TestCase):
    def extract(self, value):
        source = RUNNER.read_text()
        function = 'extract_target_msa_from_yaml() {' + source.split(
            'extract_target_msa_from_yaml() {', 1)[1].split('\nextract_chain_msa_from_yaml()', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / 'input.yaml'
            template.write_text('sequences:\n- protein:\n    id: A\n    sequence: ACDE\n'
                                '    msa: binder.a3m\n- protein:\n    id: B\n'
                                '    sequence: FGHI\n    msa: ' + value + '\n')
            result = subprocess.run(['/bin/bash', '-c', function +
                '\nextract_target_msa_from_yaml "$1" B', 'test', str(template)],
                check=True, capture_output=True, text=True)
            return result.stdout.strip()

    def test_auto_enters_resolution_instead_of_file_validation(self):
        for value in ('auto', 'AUTO', '"auto"', "'auto'"):
            with self.subTest(value=value):
                self.assertEqual(self.extract(value), '')

    def test_other_non_path_policies_remain_non_paths(self):
        for value in ('empty', 'none', 'null'):
            with self.subTest(value=value):
                self.assertEqual(self.extract(value), '')

    def test_explicit_alignment_paths_remain_unchanged(self):
        for value in ('target.a3m', '/tmp/target.a3m', 'alignments/auto.a3m'):
            with self.subTest(value=value):
                self.assertEqual(self.extract(value), value)


if __name__ == '__main__':
    unittest.main()
