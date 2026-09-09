#!/usr/bin/env python3
"""Execute the real per-run scheduler with synthetic prediction/MPNN adapters.

Requires the explicitly selected Biotite/PyYAML test interpreter. No model loads,
GPU jobs, reference proteins, targets or experimental acceptance claims.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "Sources/iProteinStudio/Resources/pipeline"
sys.path.insert(0, str(PIPELINE / "scripts"))
from initialization_assessment import assess_structure
from initialization_refinement import Refinement, validate_monomer_template


def fixture_command(command, *args):
    import yaml
    from biotite.sequence import ProteinSequence
    if command == "yaml":
        output, sequence = args
        Path(output).write_text(yaml.safe_dump({"version": 1, "sequences": [
            {"protein": {"id": "A", "sequence": sequence, "msa": "empty"}}]}))
    elif command == "sequence":
        print(yaml.safe_load(Path(args[0]).read_text())["sequences"][0]["protein"]["sequence"])
    elif command == "predict":
        sequence, name, directory = args
        destination = Path(directory) / "pred_min"
        destination.mkdir(parents=True, exist_ok=True)
        scenario = os.environ.get("FIXTURE_SCENARIO", "retry")
        uncertain = scenario == "exhaust" or ("cycle_00" in name and scenario != "original")
        score = 20 if uncertain else 90
        atoms = []
        for index, aa in enumerate(sequence, 1):
            residue = "UNK" if aa == "X" else ProteinSequence.convert_letter_1to3(aa)
            atoms.append(f"ATOM  {index:5d}  CA  {residue:3s} A{index:4d}    "
                         f"{(index - 1) * 3.8:8.3f}{0:8.3f}{0:8.3f}{1:6.2f}{score:6.2f}           C\n")
        structure, confidence = destination / "model_0.pdb", destination / "confidence.json"
        structure.write_text("".join(atoms) + "END\n")
        confidence.write_text(json.dumps({"synthetic": True, "plddt": score}))
        with Path(os.environ["FIXTURE_EVENTS"]).open("a") as handle:
            handle.write(json.dumps({"stage": "prediction", "name": name, "sequence": sequence}) + "\n")
        print(f"{structure}|{confidence}|nan|{score}")
    elif command == "redesign":
        cycle_dir, structure, cycle, sequence = args
        with Path(os.environ["FIXTURE_EVENTS"]).open("a") as handle:
            handle.write(json.dumps({"stage": "redesign", "cycle": int(cycle), "structure": structure}) + "\n")
        print("A" * len(sequence))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.template = self.root / "monomer.yaml"
        fixture_command("yaml", str(self.template), "A" * 24)
        source = (PIPELINE / "nanohunter_run.sh").read_text()
        functions = source[source.index("initialization_action() {"):source.index("write_binder_only_yaml() {")]
        resume = source[source.index("cycle_prediction_complete() {"):source.index("wait_for_slot() {")]
        self.driver = self.root / "driver.sh"
        settings = dict(EXPT_ROOT=str(self.root / "campaign"), TEMPLATE_YAML=str(self.template),
            PIPELINE_CODE_ROOT=str(PIPELINE), INITIALIZATION_PYTHON=sys.executable,
            INITIALIZATION_REFINEMENT_HELPER=str(PIPELINE / "scripts/initialization_refinement.py"),
            FIXTURE_PYTHON=sys.executable, FIXTURE_SCRIPT=str(Path(__file__).resolve()),
            INITIALIZATION_MAX_ATTEMPTS="0", INITIALIZATION_MIN_COIL_LENGTH="4",
            INITIALIZATION_CONFIDENCE_THRESHOLD="50", PREDICTOR="boltz", PREDICTOR_SEED="42",
            PREDICTOR_SAMPLES="1", INTELLIFOLD_MODEL="v2-flash", BOLTZ_USE_POTENTIALS_DEFAULT="0",
            BOLTZ_EXTRA_CLI_STRING="", INTELLIFOLD_EXTRA_CLI_STRING="",
            WORKFLOW="protein", SCAFFOLD_FROM_TEMPLATE="0", MOTIF_SCAFFOLDING="0", PARTIAL_REDESIGN="0",
            BINDER_MIN_LEN="24", BINDER_MAX_LEN="24", BINDER_PERCENT_X="50", BINDER_RANDOM_SEED="10",
            HELIX_KILL="0", NEGATIVE_HELIX_CONSTANT="0.5", LOOP_KILL="0", RESUME="1",
            N_CYCLES="2", INITIAL_STRUCTURE="", SEQUENCE_DESIGNER_LABEL="synthetic",
            ANTIFOLD_NANOBODY_CHAIN="A")
        self.driver.write_text("#!/bin/bash\nset -euo pipefail\n" +
            "\n".join(f"{key}={shlex.quote(value)}" for key, value in settings.items()) + "\n" + resume + functions + r'''
die() { echo "ERROR: $*" >&2; exit 1; }
now_epoch() { echo 1; }
calc_duration() { echo 0; }
pick_target_msa_for_predictor() { echo ""; }
make_masked_nanobody_scaffold_msa() { echo ""; }
make_yaml_with_binder_sequence() { "$FIXTURE_PYTHON" "$FIXTURE_SCRIPT" --fixture yaml "$2" "$3"; }
extract_binder_sequence_from_yaml() { "$FIXTURE_PYTHON" "$FIXTURE_SCRIPT" --fixture sequence "$1"; }
normalize_predictor_result_line() { echo "$1"; }
extract_metrics_from_conf_json() { echo "nan,90"; }
export_cif() { :; }
generate_random_binder_seq() {
  "$FIXTURE_PYTHON" "$PIPELINE_CODE_ROOT/scripts/secondary_structure_control.py" seed \
    --min-length "$1" --max-length "$2" --percent-x "$3" --predictor "$7" --seed "$8" \
    --secondary-bias antihelix --secondary-bias-scope seed-only --anti-helix-strength "$5" --plan "$9"
}
run_predictor_once() { "$FIXTURE_PYTHON" "$FIXTURE_SCRIPT" --fixture predict "$3" "$4" "$5"; }
run_sequence_redesign() { "$FIXTURE_PYTHON" "$FIXTURE_SCRIPT" --fixture redesign "$1" "$2" "$3" "$7"; }
run_one_design 1 ""
''')
        self.environment = {**os.environ, "FIXTURE_EVENTS": str(self.root / "events.jsonl"),
                            "MPLCONFIGDIR": str(self.root / "matplotlib")}

    def run_driver(self, scenario="retry"):
        return subprocess.run(["bash", str(self.driver)], env={**self.environment, "FIXTURE_SCENARIO": scenario},
                              capture_output=True, text=True, timeout=45)

    def events(self):
        return [json.loads(line) for line in (self.root / "events.jsonl").read_text().splitlines()]

    def test_initialization_then_normal_cycling_and_no_work_resume(self):
        result = self.run_driver("original")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events = self.events()
        self.assertEqual([e["stage"] for e in events],
                         ["prediction", "redesign", "prediction", "redesign", "prediction"])
        run = self.root / "campaign/run_001"
        self.assertFalse((run / "initialization_refinement").exists())
        original = (run / "cycle_00/pred_min/model_0.pdb").read_bytes()
        result = self.run_driver("original")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.events(), events)
        self.assertEqual((run / "cycle_00/pred_min/model_0.pdb").read_bytes(), original)
        self.assertEqual(len((run / "metrics_per_cycle.csv").read_text().splitlines()), 4)

    def test_rejects_conditioned_or_multichain_templates(self):
        validate_monomer_template(self.template)
        import yaml
        document = yaml.safe_load(self.template.read_text())
        invalid = [dict(document, constraints=[]), dict(document, sequences=document["sequences"] * 2),
                   {"sequences": [{"ligand": {"id": "A", "smiles": "C"}}]}]
        for value in invalid:
            self.template.write_text(yaml.safe_dump(value))
            with self.assertRaises(ValueError):
                validate_monomer_template(self.template)

    def test_full_cli_preflight_accepts_monomer_and_rejects_unsupported_policy(self):
        runtime = self.root / "runtime"
        for name in ("boltz", "protenix", "ligandmpnn"):
            interpreter = runtime / f"venvs/NanoHunter_{name}/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n")
            interpreter.chmod(0o755)
        for name in ("run.py", "model_params/solublempnn_v_48_020.pt"):
            path = runtime / "src/LigandMPNN" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()  # Empty existence-check fixture; no model weights.
        command = ["bash", str(PIPELINE / "nanohunter_run.sh"), "--workflow", "protein",
                   "--predictor", "boltz", "--sequence-designer", "solublempnn", "--random-binder",
                   "--binder-random-seed", "11", "--binder-min-len", "24", "--binder-max-len", "24",
                   "--template-yaml", str(self.template), "--post-predictor", "none", "--post-mode", "none",
                   "--max-parallel", "1", "--throughput-profile", "off", "--target-msa-mode", "off",
                   "--initialization-max-attempts", "3", "--initialization-min-coil-length", "4",
                   "--initialization-confidence-threshold", "50", "--check-config"]
        env = {**self.environment, "NANOHUNTER_ROOT": str(runtime),
               "IPROTEINSTUDIO_PIPELINE_SNAPSHOT": str(PIPELINE)}
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Retired secondary-structure control", result.stderr)

    def test_real_coordinate_adapter_rejects_sequence_and_confidence_errors(self):
        self.assertEqual(self.run_driver("original").returncode, 0)
        run = self.root / "campaign/run_001"
        status = {"structure": str(run / "cycle_00/pred_min/model_0.pdb"),
                  "sequence": self.events()[0]["sequence"]}
        policy = dict(max_attempts=3, min_uncertain_coil_length=4, confidence_threshold=50)
        result = assess_structure(Path(status["structure"]), status["sequence"], policy)
        self.assertEqual(len(result["psea"]), 24)
        self.assertTrue(result["eligible"])
        with self.assertRaisesRegex(ValueError, "sequence differs"):
            assess_structure(Path(status["structure"]), "C" * 24, policy)
        bad = self.root / "bad.pdb"
        bad.write_text(Path(status["structure"]).read_text().replace(" 90.00", "101.00"))
        with self.assertRaisesRegex(ValueError, "0–100"):
            assess_structure(bad, status["sequence"], policy)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fixture":
        fixture_command(*sys.argv[2:])
    else:
        unittest.main()
