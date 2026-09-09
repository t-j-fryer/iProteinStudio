"""Native/MCP job ownership contracts; temporary fake workers, no inference."""
import fcntl
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MCP = Path(__file__).resolve().parents[1] / "Sources/iProteinStudio/Resources/pipeline/mcp"
sys.path.insert(0, str(MCP))
from iprotein_mcp import broker, common, plans
from iprotein_mcp.desktop import desktop_plan


class DesktopJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-desktop-jobs-")
        self.root = Path(self.temporary.name).resolve()
        self.environment = dict(os.environ)
        os.environ["NANOHUNTER_ROOT"] = str(self.root)
        os.environ["IPROTEINSTUDIO_TEST_SUPPORT_ROOT"] = str(self.root)
        os.environ["IPROTEINSTUDIO_AGENT_ROOT"] = str(self.root / "agent")
        (self.root / "projects/demo").mkdir(parents=True)
        (self.root / "rfd3_scripts").mkdir()
        self.script = self.root / "rfd3_scripts/predict_batch.py"
        self.script.write_text('''import argparse, json, os, pathlib, signal, subprocess, sys, time
p=argparse.ArgumentParser(); p.add_argument('--config'); a=p.parse_args()
c=json.loads(pathlib.Path(a.config).read_text()); out=pathlib.Path(c['output']); out.mkdir(parents=True,exist_ok=True)
r=pathlib.Path(os.environ['NANOHUNTER_ROOT'])
if c.get('descendant'):
 child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'])
 (out/'child.pid').write_text(str(child.pid))
 time.sleep(30)
else:
 try: (r/'active').mkdir()
 except FileExistsError: (r/'overlap').write_text('overlap')
 (out/'started').write_text('started')
 time.sleep(0.5)
 (r/'active').rmdir()
 (out/'run_summary.json').write_text('{}')
print('PBSTAGE|done|100|Finished',flush=True)
''')
        self.jobs = []

    def tearDown(self):
        for job in self.jobs:
            try:
                state = broker.load_state(job)
                if state["status"] not in broker.TERMINAL:
                    broker.cancel_job(job)
                    self.wait(job)
            except Exception:
                pass
        os.environ.clear(); os.environ.update(self.environment)
        self.temporary.cleanup()

    def native(self, name="native", **settings):
        output = self.root / "projects/demo/prediction_runs" / name
        output.mkdir(parents=True)
        common.atomic_json(output / "prediction_config.json", {"output": str(output), "predictors": ["boltz"], **settings})
        plan = desktop_plan({"project": "demo", "workflow": "prediction", "output": str(output)})
        state = broker.start_job(plan["id"], plan["sha256"])
        self.jobs.append(state["id"])
        return state, output

    def wait(self, identifier):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            state = broker.load_state(identifier)
            if state["status"] in broker.TERMINAL:
                return state
            time.sleep(0.05)
        self.fail("worker did not finish: " + str(state))

    def test_prediction_template_plans_import_validate_and_freeze_artifacts(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        helper = scripts / "prediction_templates.py"
        shutil.copyfile(MCP.parent / "scripts/prediction_templates.py", helper)
        source = self.root / "synthetic.pdb"
        source.write_text("synthetic fixture; no inference in this test")
        request = {"predictors": ["boltz"], "template": {"path": str(source), "chains": ["A"]},
                   "jobs": [{"name": "monomer", "chains": [{"id": "A", "kind": "protein", "sequence": "ACDEFG", "msa": "empty"}]}]}
        mcp = plans.prediction_plan({"project": "demo", "request": request})
        imported = Path(mcp["normalized_request"]["config"]["template"]["path"])
        self.assertNotEqual(imported, source)
        self.assertEqual(imported.read_bytes(), source.read_bytes())
        output = self.root / "projects/demo/prediction_runs/template"
        output.mkdir(parents=True)
        common.atomic_json(output / "prediction_config.json", {"output": str(output), **request})
        native = desktop_plan({"project": "demo", "workflow": "prediction", "output": str(output)})
        for plan, expected in [(mcp, imported), (native, source)]:
            paths = {item["path"] for item in plan["provenance"]}
            self.assertIn(str(expected), paths)
            self.assertIn(str(helper), paths)
        request["predictors"] = ["protenix-mini"]
        with self.assertRaisesRegex(common.StudioError, "supports"):
            plans.prediction_plan({"project": "demo", "request": request})

    def test_native_and_mcp_share_execution_ownership(self):
        first, output = self.native()
        plan = plans.prediction_plan({"project": "demo", "request": {
            "predictors": ["boltz"], "jobs": [{"name": "mcp", "chains": [{"id": "A", "kind": "protein", "sequence": "ACDEFG", "msa": "empty"}]}]}})
        second = broker.start_job(plan["id"], plan["sha256"])
        self.jobs.append(second["id"])
        self.assertEqual(self.wait(first["id"])["status"], "completed")
        self.assertEqual(self.wait(second["id"])["status"], "completed")
        self.assertFalse((self.root / "overlap").exists())
        self.assertEqual(json.loads((output / "studio_job.json").read_text())["id"], first["id"])
        self.assertTrue((common.agent_root() / "jobs" / first["id"] / "bridge/studioctl.py").is_file())

    def test_code_change_while_queued_fails_before_execution(self):
        with (common.agent_root() / "execution.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            job, output = self.native()
            self.script.write_text(self.script.read_text() + "\n# changed after planning\n")
        result = self.wait(job["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("changed after preflight", result["message"])
        self.assertFalse((output / "started").exists())

    def test_queued_input_edit_fails_before_execution(self):
        with (common.agent_root() / "execution.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            job, output = self.native()
            (output / "prediction_config.json").write_text('{}')
        self.assertEqual(self.wait(job["id"])["status"], "failed")
        self.assertFalse((output / "started").exists())

    def test_stop_waits_for_resistant_descendant_before_next_job(self):
        job, output = self.native(descendant=True)
        deadline = time.monotonic() + 5
        while not (output / "child.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child = int((output / "child.pid").read_text())
        following, next_output = self.native("following")
        state = broker.cancel_job(job["id"])
        self.assertEqual(state["status"], "stopping")
        time.sleep(0.3)
        self.assertFalse((next_output / "started").exists())
        self.assertEqual(broker.resume_job(job["id"])["status"], "stopping")
        self.assertEqual(self.wait(job["id"])["status"], "cancelled")
        self.assertFalse(common.process_alive(child))
        self.assertEqual(self.wait(following["id"])["status"], "completed")

    def test_iterative_nesso_is_a_separate_post_campaign_step(self):
        output = self.root / "projects/demo/ligand"
        snapshot = output / "pipeline-snapshot"
        (snapshot / "scripts").mkdir(parents=True)
        runner = snapshot / "nanohunter_run.sh"
        runner.write_text("#!/bin/sh\nprintf 'design\\n' > completed-design.txt\n")
        runner.chmod(0o755)
        checker = output / "fake_screen.py"
        checker.write_text("from pathlib import Path\nassert Path('pipeline-snapshot/completed-design.txt').is_file()\nPath('screened.txt').write_text('after design')\n")
        args = ["--out-root", str(output.parent), "--run-name", output.name]
        options = dict(enabled=True, topK=3, predictor="boltz", intellifoldModel="v2-flash")
        common.atomic_json(output / "studio_run.json", {"pipelineSnapshot": str(snapshot), "arguments": args,
            "request": {"targetKind": "ligand", "targetSmiles": "CCO", "nesso": options}})
        step = {"command": [sys.executable, str(checker)], "cwd": str(output), "stage": "nesso-verification"}
        with patch("iprotein_mcp.ligand_screening.prepare", return_value=(step, [checker])) as prepare:
            plan = desktop_plan({"project": "demo", "workflow": "iterative", "output": str(output)})
            prepare.assert_called_once_with(self.root, output, "iterative", options, "CCO")
        self.assertEqual([s["stage"] for s in plan["normalized_request"]["steps"]], ["iterative-design", "nesso-verification"])
        self.assertIn(str(checker), [p["path"] for p in plan["provenance"]])
        job = broker.start_job(plan["id"], plan["sha256"]); self.jobs.append(job["id"])
        self.assertEqual(self.wait(job["id"])["status"], "completed")
        self.assertTrue((output / "screened.txt").is_file())

    def test_iterative_preserves_recorded_command_and_environment(self):
        output = self.root / "projects/demo/iterative"
        snapshot = output / "pipeline-snapshot"
        (snapshot / "scripts").mkdir(parents=True)
        runner = snapshot / "nanohunter_run.sh"
        runner.write_text("#!/bin/sh\nprintf '%s\\n' NHEND\n")
        runner.chmod(0o755)
        template = output / "template.yaml"
        template.write_text("sequences: []\n")
        arguments = ["--template-yaml", str(template), "--out-root", str(output.parent),
                     "--run-name", output.name, "--design-scheduler", "cycle-wave", "--wave-batch-size", "4"]
        common.atomic_json(output / "studio_run.json", {"pipelineSnapshot": str(snapshot), "arguments": arguments})
        plan = desktop_plan({"project": "demo", "workflow": "iterative", "output": str(output)})
        self.assertEqual(plan["normalized_request"]["steps"][0]["command"][3:], arguments + ["--resume"])
        job = broker.start_job(plan["id"], plan["sha256"])
        self.jobs.append(job["id"])
        self.assertEqual(self.wait(job["id"])["status"], "completed")
        self.assertEqual(json.loads((output / "studio_run.json").read_text())["arguments"], arguments)

    def test_preparation_checkpoint_is_reused_and_rejects_changed_inputs(self):
        output = self.root / "projects/demo/rfd3"
        (output / "config").mkdir(parents=True)
        job_id = "job-preparation-test"
        common.atomic_json(broker.state_path(job_id), {"id": job_id, "status": "running"})
        plan = {"id": "plan-test", "sha256": "digest", "normalized_request": {
            "workflow": "rfdiffusion3", "output": str(output), "steps": [
                {"stage": "prepare", "command": ["prepare"], "cwd": str(output)},
                {"stage": "rfd3", "command": ["runner"], "cwd": str(output)}]}}
        calls = []
        def run(_job, command, _cwd, _env):
            calls.append(command[0])
            if command == ["prepare"]:
                common.atomic_json(output / "config/campaign.json", {"target": "saved"})
                return 0
            return 1
        with patch.object(broker, "_run_logged", side_effect=run):
            self.assertEqual(broker._execute_desktop(job_id, plan), 1)
            self.assertEqual(broker._execute_desktop(job_id, plan), 1)
            self.assertEqual(calls, ["prepare", "runner", "runner"])
            (output / "config/campaign.json").write_text("changed")
            with self.assertRaisesRegex(common.StudioError, "inputs changed"):
                broker._execute_desktop(job_id, plan)

    def test_active_jobs_and_plan_identity_survive_history_limits(self):
        for number in range(503):
            common.atomic_json(broker.state_path("job-history-" + str(number)), {
                "id": "job-history-" + str(number), "plan_id": "plan-" + str(number),
                "status": "completed", "created_at": str(number).zfill(4)})
        common.atomic_json(broker.state_path("job-old-active"), {
            "id": "job-old-active", "status": "queued", "created_at": "0000"})
        self.assertIn("job-old-active", [job["id"] for job in broker.list_jobs(1)])
        self.assertEqual(broker._existing_for_plan("plan-0")["id"], "job-history-0")

    def test_legacy_worker_cancellation_requires_its_original_client(self):
        common.atomic_json(broker.state_path("job-legacy"), {"id": "job-legacy", "status": "running"})
        with self.assertRaisesRegex(common.StudioError, "older worker"):
            broker.cancel_job("job-legacy")
        self.assertEqual(broker.load_state("job-legacy")["status"], "running")

    def test_output_must_belong_to_workspace(self):
        with self.assertRaises(common.StudioError):
            desktop_plan({"project": "demo", "workflow": "prediction", "output": str(self.root / "elsewhere")})


if __name__ == "__main__":
    unittest.main()
