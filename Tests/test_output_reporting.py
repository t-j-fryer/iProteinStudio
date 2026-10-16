"""CPU-only reporting regressions: unchanged records, cache invalidation and failures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
SCRIPTS = PIPELINE / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import validate_prediction_geometry as geometry
import prediction_output_reporting as reporting


def cif(x=3.8, quoted=False):
    atom = "'CA'" if quoted else 'CA'
    return ("data_test\nloop_\n_atom_site.group_PDB\n_atom_site.label_atom_id\n"
            "_atom_site.label_comp_id\n_atom_site.label_asym_id\n_atom_site.label_seq_id\n"
            "_atom_site.Cartn_x\n_atom_site.Cartn_y\n_atom_site.Cartn_z\n"
            f"ATOM {atom} ALA A 1 0.0 0.0 0.0\nATOM CA ALA A 2 {x} 0.0 0.0\n#\n")


def shell_function(name):
    source = (PIPELINE / 'nanohunter_run.sh').read_text()
    return re.search(r'^' + name + r'\(\) \{.*?^\}', source, re.M | re.S).group()


class ReportingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='output reporting ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        geometry._INSPECTION_CACHE.clear()

    def test_fast_tokenization_preserves_quoted_and_wrapped_rows(self):
        path = self.root / 'model.cif'
        for text in (cif(), cif(quoted=True), cif().replace('ALA A 2', 'ALA\nA 2'),
                     cif().replace('CA ALA', 'C\\A ALA')):
            path.write_text(text)
            expected = []
            pending = []
            for line in text.splitlines():
                if line.startswith(('data_', 'loop_', '_', '#')):
                    continue
                pending.extend(shlex.split(line, comments=False, posix=True))
                while len(pending) >= 8:
                    expected.append(pending[:8]); pending = pending[8:]
            self.assertEqual(geometry.cif_atom_rows(path)[1], expected)

    def test_cache_reuses_parse_but_not_mutable_result(self):
        path = self.root / 'model.cif'; path.write_text(cif())
        with patch.object(geometry, 'read_residues', wraps=geometry.read_residues) as reader:
            first = geometry.inspect_geometry(path)
            first['errors'].append('caller mutation')
            second = geometry.inspect_geometry(path)
            self.assertEqual(second['errors'], [])
            self.assertEqual(reader.call_count, 1)
        report = geometry.write_report(path)
        self.assertNotIn('caller mutation', json.dumps(report))

    def test_same_size_timestamp_and_threshold_changes_invalidate_cache(self):
        path = self.root / 'model.cif'; path.write_text(cif(3.8))
        timestamp = path.stat().st_mtime_ns
        self.assertFalse(geometry.inspect_geometry(path)['violations'])
        path.write_text(cif(9.8)); os.utime(path, ns=(timestamp, timestamp))
        self.assertEqual(len(geometry.inspect_geometry(path)['violations']), 1)
        with patch.object(geometry, 'MAX_CA_CA', 10.):
            self.assertFalse(geometry.inspect_geometry(path)['violations'])

    def test_symlink_retarget_and_format_are_not_stale(self):
        source = self.root / 'source.cif'; source.write_text(cif())
        bad = self.root / 'bad.cif'; bad.write_text('data_empty\n')
        link = self.root / 'model.cif'; link.symlink_to(source)
        self.assertFalse(geometry.inspect_geometry(link)['errors'])
        link.unlink(); link.symlink_to(bad)
        self.assertTrue(geometry.inspect_geometry(link)['errors'])
        pdb = self.root / 'model.pdb'; pdb.symlink_to(source)
        self.assertTrue(geometry.inspect_geometry(pdb)['errors'])

    def test_cache_is_bounded(self):
        path = self.root / 'model.cif'
        for index in range(40):
            path.write_text(cif(index)); geometry.inspect_geometry(path)
        self.assertEqual(len(geometry._INSPECTION_CACHE), geometry._CACHE_LIMIT)

    def test_resident_uses_in_process_validator_and_propagates_failure(self):
        import resident_predictor
        path = self.root / 'model.cif'; path.write_text(cif())
        with patch.object(resident_predictor.subprocess, 'run', side_effect=AssertionError('subprocess')):
            with contextlib.redirect_stdout(io.StringIO()):
                resident_predictor.validate_geometry(self.root, path)
                path.write_text('data_empty\n')
                with self.assertRaisesRegex(RuntimeError, 'unusable'):
                    resident_predictor.validate_geometry(self.root, path)

    def make_items(self):
        log = self.root / 'predict.log'; log.write_text('fixture\n')
        items = []
        for index in range(1, 4):
            source = self.root / f'source{index}'; source.mkdir()
            (source / 'model.cif').write_text(cif(index * 3.8))
            (source / 'confidence.json').write_text(json.dumps({'iPTM': index / 10, 'plddt': 75}))
            items.append([str(source / 'model.cif'), str(source / 'confidence.json'),
                          str(self.root / f'run_{index:03d}/cycle_01/pred_min'),
                          str(self.root / f'run_{index:03d}/cycle_01/predictor')])
        return items, log

    def invoke_batch(self, items, log, workers=1):
        args = [sys.executable, str(SCRIPTS / 'prediction_output_reporting.py'), 'finalize',
                '--log', str(log), '--predictor', 'fixture', '--start', '10', '--end', '20',
                '--duration', '10', '--workers', str(workers)]
        for item in items:
            args += ['--item'] + item
        return subprocess.run(args, capture_output=True, text=True)

    def test_batch_and_parallel_reporting_produce_same_files_and_references(self):
        items, log = self.make_items()
        first = self.invoke_batch(items, log)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, '')
        before = {str(p): p.read_bytes() for p in self.root.glob('run_*/cycle_01/pred_min/*')}
        second = self.invoke_batch(items, log, 2)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.glob('run_*/cycle_01/pred_min/*')})
        for item in items:
            directory = Path(item[2])
            self.assertEqual((directory / 'model_0.cif').resolve(), Path(item[0]).resolve())
            self.assertFalse(os.readlink(directory / 'model_0.cif').startswith('/'))
            report = json.loads((directory / 'geometry_report.json').read_text())
            self.assertEqual(report['structures'][0]['path'], 'model_0.cif')

    def test_failed_item_has_no_timing_and_can_be_retried(self):
        items, log = self.make_items()
        Path(items[1][0]).write_text('data_empty\n')
        result = self.invoke_batch(items, log)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((Path(items[0][2]) / 'wave_predict_end.txt').exists())
        self.assertFalse((Path(items[1][2]) / 'wave_predict_end.txt').exists())
        self.assertFalse((Path(items[2][2]) / 'wave_predict_end.txt').exists())
        Path(items[1][0]).write_text(cif())
        self.assertEqual(self.invoke_batch(items, log).returncode, 0)

    def test_metrics_precedence_missing_and_bad_values(self):
        path = self.root / 'confidence.json'
        path.write_text(json.dumps({'nested': {'iptm': 0.1}, 'iPTM': .7, 'plddt': [1, 2]}))
        self.assertEqual(str(reporting.confidence_metrics(path)), '(0.7, nan)')
        path.write_text('broken')
        self.assertEqual(str(reporting.confidence_metrics(path)), '(nan, nan)')

    def test_shell_batch_and_recording_execute_against_fixture_outputs(self):
        # Stub only inference; execute the actual shell normalization/reporting.
        output = self.root / '_cycle_wave/cycle_01/batch_01/protenix-v2'
        for index in (1, 2):
            tag = f'run_{index:03d}'
            cycle = self.root / tag / 'cycle_01'; cycle.mkdir(parents=True)
            (cycle / f'{tag}_cycle_01.yaml').write_text('{}')
            (cycle.parent / 'state_current_seq.txt').write_text('TEST\n')
            predicted = output / f'{tag}_cycle_01/pred_min'; predicted.mkdir(parents=True)
            (predicted / 'model_0.cif').write_text(cif())
            (predicted / 'confidence.json').write_text(json.dumps({'iptm': index / 10, 'plddt': 75}))
        (self.root / 'resident.log').write_text('stub\n')
        harness = '''set -euo pipefail
EXPT_ROOT="$1"; PIPELINE_CODE_ROOT="$2"; N_RUNS=2; RESUME=0
PREDICTOR=protenix-v2; DESIGN_SCHEDULER=resident; RESIDENT_LOG="$1/resident.log"
now_epoch() { echo 10; }
calc_duration() { echo 0; }
submit_resident_predictor_request() { return 0; }
materialize_output_reference() { ln -sfn "$1" "$2"; }
export_cif() { echo "$*" >> "${EXPT_ROOT}/exports.txt"; }
die() { echo "$*" >&2; exit 1; }
''' + shell_function('run_cycle_wave_predictor_batch') + '\n' + shell_function('record_cycle_wave_predictions') + '''
run_cycle_wave_predictor_batch 1 1 1 2
record_cycle_wave_predictions 1
'''
        result = subprocess.run(['bash', '-c', harness, 'fixture', str(self.root), str(PIPELINE)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for index in (1, 2):
            row = (self.root / f'run_{index:03d}/metrics_per_cycle.csv').read_text()
            self.assertTrue(row.startswith(f'1,{index / 10},75.0,'), row)
            self.assertTrue(row.endswith(',TEST\n'))
            self.assertEqual((self.root / f'run_{index:03d}/timing_cycles.csv').read_text(), '1,10,10,0\n')


if __name__ == '__main__':
    unittest.main()
