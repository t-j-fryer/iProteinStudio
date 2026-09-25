"""Native/MCP job ownership contracts; temporary fake workers, no inference."""
import fcntl
import json
import os
import shutil
import signal
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

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
r=pathlib.Path(FIXTURE_ROOT)
if c.get('descendant'):
 child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'], start_new_session=c.get('detached', False), close_fds=not c.get('inherit_lease', False))
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
'''.replace('FIXTURE_ROOT', repr(str(self.root))))
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
            frozen_helper = Path(plan["code_snapshot"]["path"]) / "scripts/prediction_templates.py"
            self.assertIn(str(frozen_helper), paths)
            self.assertEqual(frozen_helper.read_bytes(), helper.read_bytes())
        request["predictors"] = ["protenix-mini"]
        with self.assertRaisesRegex(common.StudioError, "supports"):
            plans.prediction_plan({"project": "demo", "request": request})

    def test_rfd3_plan_freezes_nested_runtime_helpers(self):
        output = self.root / "projects/demo/rfd3_runs/frozen"
        (output / "config").mkdir(parents=True)
        for relative in ("rfd3_scripts/prepare_campaign.py",
                         "rfd3_scripts/rfd3_protein_campaign.py",
                         "rfd3/mlx_port/sampler.py", "rfd3/scripts/rfd3_resume.py"):
            script = self.root / relative
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("# inert fixture\n")
        common.atomic_json(output / "config/studio_request.json", {
            "campaign_dir": str(output), "target_kind": "protein"})
        plan = desktop_plan({"project": "demo", "workflow": "rfdiffusion3", "output": str(output)})
        helper = self.root / "rfd3/scripts/rfd3_resume.py"
        paths = {item["path"] for item in plan["provenance"]}
        self.assertIn(str(helper), paths)
        self.assertIn(str(self.root / "rfd3/mlx_port/sampler.py"), paths)
        plans.load_plan(plan["id"], plan["sha256"])
        helper.write_text("# changed helper\n")
        with self.assertRaisesRegex(common.StudioError, "changed after preflight"):
            plans.load_plan(plan["id"], plan["sha256"])

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

    def test_protein_hunter_workspaces_queue_and_cancel_independently(self):
        def submit(workspace, name):
            output = self.root / 'projects' / workspace / name
            snapshot = output / '.studio_runtime/pipeline'
            (snapshot / 'scripts').mkdir(parents=True)
            runner = snapshot / 'nanohunter_run.sh'
            runner.write_text('''#!/usr/bin/python3
import os, pathlib, sys, time
a=sys.argv; out=pathlib.Path(a[a.index('--out-root')+1])/a[a.index('--run-name')+1]
root=pathlib.Path(FIXTURE_ROOT)
try: (root/'active').mkdir()
except FileExistsError: (root/'overlap').touch()
(out/'started').touch()
while not (out/'release').exists(): time.sleep(.05)
(out/'summary_all_runs.csv').write_text('fixture,value\\n1,1\\n')
(root/'active').rmdir()
'''.replace('FIXTURE_ROOT', repr(str(self.root))))
            runner.chmod(0o755)
            template = output / 'input.yaml'; template.write_text('inert queue fixture')
            common.atomic_json(output / 'studio_run.json', {
                'pipelineSnapshot': str(snapshot), 'arguments': ['--run-name', name,
                '--out-root', str(output.parent), '--template-yaml', str(template)]})
            plan = desktop_plan({'project': workspace, 'workflow': 'iterative', 'output': str(output)})
            state = broker.start_job(plan['id'], plan['sha256'])
            self.jobs.append(state['id'])
            return state['id'], output
        first, one = submit('workspace-one', 'first')
        deadline = time.monotonic() + 8
        while not (one / 'started').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue((one / 'started').exists())
        second, two = submit('workspace-two', 'second')
        cancelled, three = submit('workspace-two', 'third')
        self.assertEqual(broker.load_state(second)['status'], 'queued')
        self.assertFalse((two / 'started').exists())
        broker.cancel_job(cancelled)
        self.assertEqual(self.wait(cancelled)['status'], 'cancelled')
        self.assertFalse((three / 'started').exists())
        self.assertEqual(broker.load_state(first)['status'], 'running')
        (two / 'release').touch(); (one / 'release').touch()
        self.assertEqual(self.wait(first)['status'], 'completed')
        self.assertEqual(self.wait(second)['status'], 'completed')
        self.assertFalse((self.root / 'overlap').exists())
        for output in (one, two):
            self.assertTrue((output / 'summary_all_runs.csv').is_file())

    def test_cancel_before_worker_ready_keeps_durable_intent(self):
        identifier = 'job-startup-fixture'
        path = broker.state_path(identifier)
        common.atomic_json(path, {'id': identifier, 'status': 'queued', 'pid': 12345,
                                 'worker_contract': 2, 'cancellation_contract': 1})
        with patch.object(broker, 'process_alive', return_value=True), patch.object(broker.os, 'kill') as kill:
            self.assertEqual(broker.cancel_job(identifier)['status'], 'stopping')
            kill.assert_not_called()
        # A concurrent progress/status update cannot erase the stop request.
        broker._update(identifier, status='running')
        self.assertTrue(broker._cancelled(identifier))
        self.assertTrue((path.parent / 'cancel.json').is_file())

    def test_all_four_desktop_workflows_share_one_queue(self):
        # Build inert adapters before planning, so the real provenance checks
        # and desktop routing run unchanged. No installed engine is accessed.
        outputs = {kind: self.root / 'projects/demo' / kind
                   for kind in ('iterative', 'nise', 'rfdiffusion3', 'prediction')}
        for output in outputs.values():
            output.mkdir(parents=True)
            common.atomic_json(output / 'studio_run_label.json', {'name': 'Trial α / ' + output.name})
        worker = self.script.read_text().replace('a=p.parse_args()', 'a,_=p.parse_known_args()')
        for relative in ('rfd3/.venv/bin/python', 'venvs/NanoHunter_boltz/bin/python'):
            python = self.root / relative
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
        nise_snapshot = outputs['nise'] / '.studio_runtime/pipeline'
        nise_scripts = nise_snapshot / 'scripts/nise'
        nise_scripts.mkdir(parents=True)
        (nise_scripts / 'contract.py').write_text('# inert contract fixture\n')
        (nise_scripts / 'campaign.py').write_text(worker)
        common.atomic_json(outputs['nise'] / 'nise_config.json', {'output': str(outputs['nise']), 'request': {}})
        config = outputs['rfdiffusion3'] / 'config'
        config.mkdir()
        common.atomic_json(config / 'studio_request.json', {
            'campaign_dir': str(outputs['rfdiffusion3']), 'target_kind': 'protein'})
        (self.root / 'rfd3_scripts/prepare_campaign.py').write_text(
            "import json,pathlib,sys\np=pathlib.Path(sys.argv[1]); c=json.loads(p.read_text())\n"
            "(p.parent/'campaign.json').write_text(json.dumps({'output':c['campaign_dir']}))\n")
        (self.root / 'rfd3_scripts/rfd3_protein_campaign.py').write_text(worker)
        common.atomic_json(outputs['prediction'] / 'prediction_config.json', {'output': str(outputs['prediction'])})
        iterative = outputs['iterative']
        snapshot = iterative / '.studio_runtime/pipeline'
        snapshot.mkdir(parents=True)
        # The iterative entry point receives its normal saved argv; this inert
        # fixture reads only the output file and marks lease overlap.
        (snapshot / 'nanohunter_run.sh').write_text(
            '#!/usr/bin/env python3\n' + worker.replace(
                "c=json.loads(pathlib.Path(a.config).read_text())", f"c={{'output': {str(iterative)!r}}}"))
        common.atomic_json(iterative / 'studio_run.json', {'pipelineSnapshot': str(snapshot),
            'arguments': ['--out-root', str(iterative.parent), '--run-name', iterative.name]})
        # Keep the executable entry point shaped like the production runner.
        (snapshot / 'fixture.py').write_text((snapshot / 'nanohunter_run.sh').read_text())
        (snapshot / 'nanohunter_run.sh').write_text(f'#!/bin/sh\nexec "{sys.executable}" "{snapshot}/fixture.py" "$@"\n')
        (snapshot / 'nanohunter_run.sh').chmod(0o755)
        contract = Mock()
        contract.preflight.return_value = {'backbone_method': 'hallucination'}
        contract.required_files.return_value = []
        contract.prediction_budget.return_value = {}
        submitted = []
        with (common.agent_root() / 'execution.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with patch('iprotein_mcp.nise.contract', return_value=contract):
                for workflow, output in outputs.items():
                    plan = desktop_plan({'project': 'demo', 'workflow': workflow, 'output': str(output)})
                    state = broker.start_job(plan['id'], plan['sha256'])
                    self.jobs.append(state['id']); submitted.append(state['id'])
                    self.assertEqual(state['status'], 'queued')
                    self.assertEqual(state['display_name'], 'Trial α / ' + workflow)
                    self.assertFalse((output / 'started').exists())
        for identifier in submitted:
            result = self.wait(identifier)
            self.assertEqual(result['status'], 'completed', str(result))
        self.assertFalse((self.root / 'overlap').exists())
        self.assertTrue(all((output / 'started').exists() for output in outputs.values()))

    def test_resume_clears_cancel_marker_before_spawning(self):
        identifier = 'job-resume-fixture'
        path = broker.state_path(identifier)
        common.atomic_json(path, {'id': identifier, 'status': 'cancelled', 'pid': None,
                                 'worker_contract': 2, 'cancellation_contract': 1})
        common.atomic_json(path.parent / 'cancel.json', {'requested_at': 'fixture'})
        def spawn(job):
            self.assertFalse((path.parent / 'cancel.json').exists())
            self.assertFalse(broker._cancelled(job))
            return broker.load_state(job)
        with patch.object(broker, '_spawn', side_effect=spawn):
            self.assertEqual(broker.resume_job(identifier)['status'], 'queued')

    def test_code_update_while_queued_preserves_original_execution(self):
        with (common.agent_root() / "execution.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            job, output = self.native()
            self.script.write_text("raise AssertionError('New adapter must not replace queued code')\n")
        result = self.wait(job["id"])
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue((output / "started").exists())
        self.assertTrue((output / "run_summary.json").exists())

    def test_queued_input_edit_fails_before_execution(self):
        with (common.agent_root() / "execution.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            job, output = self.native()
            (output / "prediction_config.json").write_text('{}')
        self.assertEqual(self.wait(job["id"])["status"], "failed")
        self.assertFalse((output / "started").exists())

    def test_queued_run_name_is_frozen_with_the_plan(self):
        output = self.root / 'projects/demo/prediction_runs/named'
        output.mkdir(parents=True)
        common.atomic_json(output / 'prediction_config.json', {'output': str(output)})
        label = output / 'studio_run_label.json'
        common.atomic_json(label, {'name': 'Trial α / repeat'})
        with (common.agent_root() / 'execution.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            plan = desktop_plan({'project': 'demo', 'workflow': 'prediction', 'output': str(output)})
            state = broker.start_job(plan['id'], plan['sha256']); self.jobs.append(state['id'])
            self.assertEqual(state['display_name'], 'Trial α / repeat')
            common.atomic_json(label, {'name': 'Changed after submission'})
        self.assertEqual(self.wait(state['id'])['status'], 'failed')
        self.assertFalse((output / 'started').exists())

    def test_stop_waits_for_resistant_descendant_before_next_job(self):
        self.check_descendant_cancellation()

    def test_stop_reaps_new_session_descendant_with_inherited_lease(self):
        self.check_descendant_cancellation(detached=True, inherit_lease=True)

    def test_recovery_after_worker_crash_releases_inherited_lease(self):
        from iprotein_mcp.recovery import cleanup_job
        job, output = self.native(descendant=True, detached=True, inherit_lease=True)
        receipt = broker.state_path(job['id']).parent / 'processes.json'
        deadline = time.monotonic() + 6
        child = None
        while time.monotonic() < deadline:
            if (output / 'child.pid').exists():
                child = int((output / 'child.pid').read_text())
                if receipt.exists() and str(child) in common.load_json(receipt).get('known', {}):
                    break
            time.sleep(.05)
        self.assertIsNotNone(child)
        self.assertIn(str(child), common.load_json(receipt)['known'])
        worker = broker._DETACHED[job['id']]
        worker.kill()  # This test's worker only; simulate a crash, not a user Stop.
        worker.wait(timeout=5)
        self.assertEqual(broker.load_state(job['id'])['status'], 'failed')
        following, next_output = self.native('after-crash')
        time.sleep(.2)
        self.assertFalse((next_output / 'started').exists())
        report = cleanup_job(job['id'])
        self.assertFalse(report['process_ids'])
        self.assertFalse(common.process_alive(child))
        self.assertTrue(output.exists())
        self.assertEqual(self.wait(following['id'])['status'], 'completed')

    def check_descendant_cancellation(self, **options):
        job, output = self.native(descendant=True, **options)
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

    def test_openfold_resident_rejected_before_submission(self):
        output = self.root / "projects/demo/openfold"
        snapshot = output / ".studio_runtime/pipeline"
        snapshot.mkdir(parents=True)
        runner = snapshot / "nanohunter_run.sh"
        runner.write_text("#!/bin/sh\necho inert-openfold-worker\n")
        runner.chmod(0o755)
        template = output / "template.yaml"
        template.write_text("sequences: []\n")
        for scheduler in ("resident", "campaign-resident", "run"):
            with self.subTest(scheduler=scheduler):
                arguments = ["--predictor", "openfold-3-mlx", "--design-scheduler", scheduler,
                             "--template-yaml", str(template), "--out-root", str(output.parent),
                             "--run-name", output.name]
                common.atomic_json(output / "studio_run.json", {
                    "pipelineSnapshot": str(snapshot), "arguments": arguments})
                request = {"project": "demo", "workflow": "iterative", "output": str(output)}
                if scheduler != "run":
                    with self.assertRaisesRegex(common.StudioError, "OpenFold-3 has no resident worker"):
                        desktop_plan(request)
                    self.assertFalse(list((self.root / "agent/jobs").glob("*/state.json")))
                else:
                    plan = desktop_plan(request)
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
