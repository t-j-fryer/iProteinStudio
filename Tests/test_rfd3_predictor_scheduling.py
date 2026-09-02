#!/usr/bin/env python3
"""Functional contracts for RFdiffusion3 verification model scheduling."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay/scripts/run_predictors.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("rfd3_predictor_scheduler", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def executable_link(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(sys.executable)


def write_inputs(path: Path) -> None:
    path.mkdir(parents=True)
    for name in ("design_a", "design_b"):
        (path / f"{name}.yaml").write_text(textwrap.dedent(f"""\
            sequences:
              - protein:
                  id: A
                  sequence: GGGG
                  msa: empty
            version: 1
            name: {name}
        """))


class RFD3PredictorSchedulingTests(unittest.TestCase):
    def test_measured_engine_policy(self):
        runner = load_runner()
        for predictor in ("boltz", "intellifold", "protenix-mini"):
            self.assertEqual(runner.scheduling_policy(predictor), "resident")
        self.assertEqual(runner.scheduling_policy("protenix-v2"), "cycle-wave")
        self.assertEqual(runner.scheduling_policy("openfold-3-mlx"), "per-input")

    def test_resident_intellifold_uses_one_worker_for_two_designs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            runtime = base / "runtime"
            inputs = base / "inputs"
            output = base / "output"
            executable_link(runtime / "venvs/NanoHunter_intellifold/bin/python")
            write_inputs(inputs)
            worker = runtime / "scripts/resident_predictor.py"
            worker.parent.mkdir(parents=True)
            worker.write_text(textwrap.dedent("""\
                import argparse, json, os, time
                from pathlib import Path
                p=argparse.ArgumentParser(); p.add_argument('--config', required=True); a=p.parse_args()
                config=json.load(open(a.config)); queue=Path(config['queue'])
                def emit(path, value):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp=path.with_suffix(path.suffix+'.part')
                    tmp.write_text(json.dumps(value)); tmp.replace(path)
                emit(queue/'ready.json', {'pid':os.getpid(),'device':'mps','fallback':0,'model_load_count':1})
                while not (queue/'stop.json').exists():
                    for request in sorted((queue/'requests').glob('request_*.json')):
                        response=queue/'responses'/request.name
                        if response.exists(): continue
                        data=json.loads(request.read_text()); source=Path(data['input_dir']); out=Path(data['output_dir'])
                        for item in source.glob('*.yaml'):
                            leaf=out/'inputs'/'predictions'/item.stem; leaf.mkdir(parents=True, exist_ok=True)
                            (leaf/f'{item.stem}_summary_confidences.json').write_text(json.dumps({'iptm':0.75,'plddt':0.8}))
                            (leaf/f'{item.stem}.cif').write_text('data_prediction\\n')
                        emit(response, {'ok':True,'request_id':data['request_id'],'completed_jobs':1,
                                        'model_load_count':1,'wall_seconds':0.01})
                    time.sleep(0.01)
                emit(queue/'stopped.json', {'pid':os.getpid(),'model_load_count':1})
            """))
            completed = subprocess.run([
                sys.executable, str(RUNNER), "--inputs", str(inputs),
                "--output", str(output), "--predictors", "intellifold",
                "--nanohunter-root", str(runtime),
            ], text=True, capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            with (output / "prediction_metrics.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["scheduler"] for row in rows}, {"resident"})
            self.assertEqual({row["model_load_count"] for row in rows}, {"1"})
            sessions = list((output / "_scheduler").glob("resident_intellifold_*"))
            self.assertEqual(len(sessions), 1)
            self.assertEqual(len(list((sessions[0] / "responses").glob("*.json"))), 2)

    def test_full_protenix_v2_uses_one_directory_wave(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            runtime = base / "runtime"
            inputs = base / "inputs"
            output = base / "output"
            executable_link(runtime / "venvs/NanoHunter_protenix/bin/python")
            write_inputs(inputs)
            adapter = runtime / "scripts/protenix_predict.py"
            adapter.parent.mkdir(parents=True)
            adapter.write_text(textwrap.dedent("""\
                import argparse, json
                from pathlib import Path
                p=argparse.ArgumentParser(); p.add_argument('--inputs', required=True); p.add_argument('--output', required=True)
                p.add_argument('--nanohunter-root'); p.add_argument('--model'); a=p.parse_args()
                source=Path(a.inputs); output=Path(a.output); output.mkdir(parents=True, exist_ok=True)
                marker=output/'model_loads.txt'; marker.write_text((marker.read_text() if marker.exists() else '')+'load\\n')
                for item in source.glob('*.yaml'):
                    leaf=output/item.stem/'pred_min'; leaf.mkdir(parents=True, exist_ok=True)
                    (leaf/'confidence.json').write_text(json.dumps({'iptm':0.7,'plddt':0.8}))
                    (leaf/'model_0.cif').write_text('data_prediction\\n')
            """))
            completed = subprocess.run([
                sys.executable, str(RUNNER), "--inputs", str(inputs),
                "--output", str(output), "--predictors", "protenix-v2",
                "--nanohunter-root", str(runtime),
            ], text=True, capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            with (output / "prediction_metrics.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["scheduler"] for row in rows}, {"cycle-wave"})
            self.assertEqual((output / "protenix-v2/model_loads.txt").read_text(), "load\n")
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["scheduling"]["protenix-v2"], "cycle-wave")


if __name__ == "__main__":
    unittest.main()
