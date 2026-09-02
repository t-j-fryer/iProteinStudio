import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = (Path(__file__).parents[1] / "Sources" / "iProteinStudio" / "Resources"
          / "rfd3" / "predict_batch.py")
SPEC = importlib.util.spec_from_file_location("predict_batch", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MSAFailureDiagnosticsTests(unittest.TestCase):
    def test_summary_retains_network_cause_not_progress_noise(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "msa.log"
            log.write_text(
                "SUBMIT 20%\rSUBMIT 80%\n"
                "Error while fetching result from MSA server. Retrying...\n"
                "HTTPSConnectionPool: certificate verify failed\n"
            )
            summary = MODULE.msa_log_summary(log)
            self.assertIn("certificate verify failed", summary)
            self.assertNotIn("SUBMIT 80%", summary)

    def test_protenix_route_retries_and_accepts_third_valid_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runtime"
            cache = Path(directory) / "cache"
            binary = root / "venvs" / "NanoHunter_protenix" / "bin" / "protenix"
            python = binary.parent / "python"
            adapter = root / "scripts" / "protenix_msa.py"
            for path in (binary, python, adapter):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("placeholder")
            sequence = "ACDEFGHIKLMNPQRSTVWY"
            calls = 0

            def fake_run(command, **kwargs):
                nonlocal calls
                calls += 1
                kwargs["stdout"].write(f"temporary connection failure {calls}\n")
                if calls == 3:
                    output = Path(command[command.index("--output") + 1])
                    output.write_text(f">query\n{sequence}\n>hit\n{sequence}\n")
                    return SimpleNamespace(returncode=0)
                return SimpleNamespace(returncode=1)

            with mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(MODULE.time, "sleep"):
                path, detail = MODULE.generate_msa(
                    sequence, cache, root, {}, "protenix"
                )
            self.assertEqual(calls, 3)
            self.assertIsNotNone(path)
            self.assertEqual(detail, "")
            self.assertTrue(MODULE.valid_a3m(path, sequence))

    def test_failed_route_preserves_log_and_reports_real_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runtime"
            cache = Path(directory) / "cache"
            binary = root / "venvs" / "NanoHunter_protenix" / "bin" / "protenix"
            python = binary.parent / "python"
            adapter = root / "scripts" / "protenix_msa.py"
            for path in (binary, python, adapter):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("placeholder")

            def fake_run(_command, **kwargs):
                kwargs["stdout"].write("ConnectTimeout: api.colabfold.com timed out\n")
                return SimpleNamespace(returncode=1)

            with mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(MODULE.time, "sleep"):
                path, detail = MODULE.generate_msa(
                    "ACDEFGHIKLMNPQRSTVWY", cache, root, {}, "protenix"
                )
            self.assertIsNone(path)
            self.assertIn("timed out", detail)
            logs = list(cache.rglob("msa.log"))
            self.assertEqual(len(logs), 1)
            self.assertIn("attempt 3/3", logs[0].read_text())

    def test_boltz_retry_never_reuses_a_corrupt_archive_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runtime"
            cache = Path(directory) / "cache"
            boltz = root / "venvs" / "NanoHunter_boltz" / "bin" / "python"
            launcher = root / "scripts" / "boltz_mps.py"
            for path in (boltz, launcher):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("placeholder")
            sequence = "ACDEFGHIKLMNPQRSTVWY"
            output_dirs = []

            def fake_run(command, **kwargs):
                output = Path(command[command.index("--out_dir") + 1])
                output_dirs.append(output)
                if len(output_dirs) == 1:
                    bad = output / "query_env" / "out.tar.gz"
                    bad.parent.mkdir(parents=True, exist_ok=True)
                    bad.write_text("not a tar archive")
                    kwargs["stdout"].write("ReadError: truncated header\n")
                    return SimpleNamespace(returncode=1)
                csv_path = output / "processed" / "msa" / "query.csv"
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                csv_path.write_text(
                    f"sequence,key\n{sequence},query\n{sequence},homologue\n"
                )
                return SimpleNamespace(returncode=0)

            with mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(MODULE.time, "sleep"):
                path, detail = MODULE.generate_msa(sequence, cache, root, {}, "boltz")
            self.assertEqual(len(output_dirs), 2)
            self.assertNotEqual(output_dirs[0], output_dirs[1])
            self.assertFalse((output_dirs[1] / "query_env" / "out.tar.gz").exists())
            self.assertIsNotNone(path)
            self.assertEqual(detail, "")
            self.assertTrue(MODULE.valid_a3m(path, sequence))


if __name__ == "__main__":
    unittest.main()
