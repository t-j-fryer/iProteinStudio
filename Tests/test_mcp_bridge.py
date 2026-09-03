#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import plistlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "Sources" / "iProteinStudio" / "Resources" / "pipeline" / "mcp"
sys.path.insert(0, str(MCP))

from iprotein_mcp import broker, catalog, common, inspect as target_inspection, plans  # noqa: E402


class MCPBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="iproteinstudio-mcp-")
        self.root = Path(self.temporary.name).resolve()
        os.environ["IPROTEINSTUDIO_TEST_SUPPORT_ROOT"] = str(self.root)
        os.environ["IPROTEINSTUDIO_AGENT_ROOT"] = str(self.root / "agent")
        (self.root / "projects" / "demo" / "inputs").mkdir(parents=True)
        (self.root / "rfd3_scripts").mkdir()
        (self.root / "rfd3").mkdir()
        self.fake_predictor = self.root / "rfd3_scripts" / "predict_batch.py"
        self.fake_predictor.write_text(
            """#!/usr/bin/env python3
import argparse, csv, json, os, time
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--config', required=True); a=p.parse_args()
cfg=json.loads(Path(a.config).read_text()); root=Path(os.environ['NANOHUNTER_ROOT'])
name=cfg['jobs'][0]['name']
active=root/'active-gpu-test'
if active.exists(): (root/'concurrency-violation').write_text('overlap')
active.write_text(str(os.getpid())); print('PBSTAGE|predict|50|fake prediction', flush=True)
if name == 'slow': time.sleep(10)
else: time.sleep(0.25)
if name == 'retry' and not (root/'retry-ready').exists():
 active.unlink(); raise SystemExit(3)
out=Path(cfg['output']); out.mkdir(parents=True, exist_ok=True)
with (out/'predictions.csv').open('w', newline='') as h:
 w=csv.DictWriter(h, fieldnames=['job','predictor','exit_code','iptm','hit']); w.writeheader(); w.writerow({'job':name,'predictor':cfg['predictors'][0],'exit_code':0,'iptm':0.75,'hit':'true'})
(out/'run_summary.json').write_text(json.dumps({'completed':1}))
active.unlink(); print('PBSTAGE|done|100|finished', flush=True)
""",
            encoding="utf-8",
        )

    def tearDown(self):
        try:
            subprocess.run(["/usr/bin/python3", str(MCP / "remote_gateway.py"), "stop"], env=os.environ, capture_output=True, timeout=5)
        except Exception:
            pass
        os.environ.pop("IPROTEINSTUDIO_TEST_SUPPORT_ROOT", None)
        os.environ.pop("IPROTEINSTUDIO_AGENT_ROOT", None)
        os.environ.pop("IPROTEINSTUDIO_CLAUDE_DESKTOP_CONFIG", None)
        self.temporary.cleanup()

    def prediction_arguments(self, name="one"):
        return {
            "project": "demo",
            "request": {
                "predictors": ["boltz"],
                "jobs": [{"name": name, "chains": [{"id": "A", "kind": "protein", "sequence": "ACDEFG", "msa": "empty"}]}],
            },
        }

    def wait_terminal(self, job_id, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = broker.load_state(job_id)
            if state["status"] in broker.TERMINAL:
                return state
            time.sleep(0.05)
        self.fail(f"job {job_id} did not finish")

    def test_stdio_protocol_and_privilege_profiles(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "contract", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "projects_list", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "iprotein://projects"}},
        ]
        completed = subprocess.run(
            ["/usr/bin/python3", str(MCP / "server.py"), "--profile", "read"],
            input="\n".join(json.dumps(value) for value in messages) + "\n",
            capture_output=True, text=True, check=True, env=os.environ,
        )
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "iproteinstudio-read")
        self.assertIn("Before planning scientific work call workflow_guide", responses[0]["result"]["instructions"])
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertIn("results_query", names)
        self.assertIn("results_overview", names)
        self.assertIn("workflow_guide", names)
        self.assertNotIn("job_start", names)
        self.assertEqual(responses[2]["result"]["structuredContent"]["projects"][0]["id"], "demo")
        projects_resource = json.loads(responses[3]["result"]["contents"][0]["text"])
        self.assertEqual(projects_resource["projects"][0]["id"], "demo")

        guide = catalog.workflow_guide("iterative_design")
        self.assertEqual(guide["defaults"]["target_template_mode"], "guide")
        self.assertTrue(any("Never template binder A" in rule for rule in guide["rules"]))

    def test_server_rejects_unknown_fields_and_cross_profile_start(self):
        module = importlib.import_module("server")
        server = module.MCPServer("run")
        result = server.dispatch({"method": "tools/call", "params": {"name": "prediction_plan", "arguments": {**self.prediction_arguments(), "typo": True}}})
        self.assertTrue(result["isError"])
        self.assertIn("unknown field", result["content"][0]["text"])
        setup = self.root / "setup_pipeline.sh"
        setup.write_text("#!/bin/bash\nexit 0\n")
        admin = plans.admin_plan({"components": ["boltz"]}, "engine_install")
        blocked = server.dispatch({"method": "tools/call", "params": {"name": "job_start", "arguments": {"plan_id": admin["id"], "plan_sha256": admin["sha256"]}}})
        self.assertTrue(blocked["isError"])
        self.assertIn("cannot start administration", blocked["content"][0]["text"])
        denied = subprocess.run(
            ["/usr/bin/python3", str(MCP / "server.py"), "--profile", "admin"],
            input="", capture_output=True, text=True, env=os.environ,
        )
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("requires IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1", denied.stderr)

    def test_prediction_plan_is_immutable_and_provenance_checked(self):
        plan = plans.prediction_plan(self.prediction_arguments())
        self.assertEqual(plan["normalized_request"]["config"]["jobs"][0]["chains"][0]["msa"], "empty")
        self.assertTrue(plan["normalized_request"]["output"].startswith(str(self.root / "projects" / "demo")))
        plans.load_plan(plan["id"], plan["sha256"])
        self.fake_predictor.write_text(self.fake_predictor.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(common.StudioError, "changed after preflight"):
            plans.load_plan(plan["id"], plan["sha256"])

    def test_iterative_target_template_plan_is_staged_and_fail_closed(self):
        runner = self.root / "nanohunter_run.sh"
        runner.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        source = self.root / "projects" / "demo" / "inputs"
        workflow = source / "target.yaml"
        workflow.write_text("sequences:\n  - protein:\n      id: A\n      sequence:\n  - protein:\n      id: B\n      sequence: ACDEFG\n", encoding="utf-8")
        structure = source / "target.pdb"
        structure.write_text("ATOM      1  CA  ALA B   1       0.000   0.000   0.000  1.00  0.00           C\n", encoding="utf-8")
        arguments = [
            "--workflow", "protein", "--predictor", "boltz",
            "--sequence-designer", "solublempnn", "--num-runs", "1",
            "--num-opt-cycles", "1", "--iptm-threshold", "0.7",
        ]
        plan = plans.iterative_plan({
            "project": "demo", "run_name": "guided", "template_path": str(workflow),
            "target_template_path": str(structure), "target_template_mode": "guide",
            "arguments": arguments,
        })
        normalized = plan["normalized_request"]
        staged = self.root / "projects" / "demo" / "guided" / "inputs" / "target_template.pdb"
        self.assertEqual(normalized["arguments"][normalized["arguments"].index("--target-template") + 1], str(staged))
        self.assertEqual(normalized["target_template_artifact"]["sha256"], common.file_digest(structure))
        self.assertNotIn("--target-template-threshold", normalized["arguments"])

        intellifold = plans.iterative_plan({
            "project": "demo", "run_name": "guided-intellifold", "template_path": str(workflow),
            "target_template_path": str(structure), "target_template_mode": "guide",
            "arguments": [value if value != "boltz" else "intellifold" for value in arguments],
        })
        self.assertIn("--target-template", intellifold["normalized_request"]["arguments"])

        with self.assertRaisesRegex(common.StudioError, "reproducibly produced broken target geometry"):
            plans.iterative_plan({
                "project": "demo", "run_name": "invalid", "template_path": str(workflow),
                "target_template_path": str(structure), "target_template_mode": "strong",
                "arguments": [value if value != "boltz" else "protenix-v2" for value in arguments],
            })
        with self.assertRaisesRegex(common.StudioError, "strong target restraint is disabled"):
            plans.iterative_plan({
                "project": "demo", "run_name": "irrelevant-threshold", "template_path": str(workflow),
                "target_template_path": str(structure), "target_template_mode": "guide",
                "target_template_threshold": 2.0, "arguments": arguments,
            })

    def test_two_mcp_jobs_share_one_execution_lock_and_results_are_queryable(self):
        first = plans.prediction_plan(self.prediction_arguments("first"))
        second = plans.prediction_plan(self.prediction_arguments("second"))
        job1 = broker.start_job(first["id"], first["sha256"])
        self.assertEqual(broker.start_job(first["id"], first["sha256"])["id"], job1["id"])
        job2 = broker.start_job(second["id"], second["sha256"])
        state1 = self.wait_terminal(job1["id"])
        state2 = self.wait_terminal(job2["id"])
        self.assertEqual(state1["status"], "completed", state1)
        self.assertEqual(state2["status"], "completed", state2)
        self.assertFalse((self.root / "concurrency-violation").exists())
        run_id = next(item["id"] for item in catalog.list_runs("demo") if item["path"] == state1["output_root"])
        results = catalog.query_results(run_id, "predictions.csv", "iptm", True, 10)
        self.assertEqual(results["distribution"]["count"], 1)
        self.assertAlmostEqual(results["distribution"]["mean"], 0.75)
        self.assertTrue((Path(state1["output_root"]) / "studio_agent_run.json").is_file())

    def test_failed_job_resumes_and_cancel_stops_the_process_group(self):
        retry_plan = plans.prediction_plan(self.prediction_arguments("retry"))
        retry_job = broker.start_job(retry_plan["id"], retry_plan["sha256"])
        failed = self.wait_terminal(retry_job["id"])
        self.assertEqual(failed["status"], "failed", failed)
        self.assertIn("status 3", failed["message"])
        self.assertTrue(failed["pipeline_log_tail"], failed)
        self.assertIn("PBSTAGE|predict", failed["error"])
        saved = json.loads(broker.state_path(retry_job["id"]).read_text())
        saved["message"] = "Workflow exited with status 3."
        broker.state_path(retry_job["id"]).write_text(json.dumps(saved))
        self.assertIn("PBSTAGE|predict", broker.load_state(retry_job["id"])["message"])
        (self.root / "retry-ready").write_text("ready\n")
        resumed = broker.resume_job(retry_job["id"])
        self.assertIn(resumed["status"], {"queued", "running"})
        completed = self.wait_terminal(retry_job["id"])
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(broker.resume_job(retry_job["id"])["status"], "completed")

        slow_plan = plans.prediction_plan(self.prediction_arguments("slow"))
        slow_job = broker.start_job(slow_plan["id"], slow_plan["sha256"])
        deadline = time.monotonic() + 5
        running = slow_job
        while time.monotonic() < deadline:
            running = broker.load_state(slow_job["id"])
            if running["status"] == "running":
                break
            time.sleep(0.05)
        self.assertEqual(running["status"], "running", running)
        pid = running["pid"]
        cancelled = broker.cancel_job(slow_job["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and common.process_alive(pid):
            broker.load_state(slow_job["id"], refresh=False)
            time.sleep(0.05)
        self.assertFalse(common.process_alive(pid))

    def test_partial_and_motif_plans_are_distinct_and_fail_closed(self):
        target = self.root / "projects" / "demo" / "inputs" / "complex.pdb"
        target.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n")
        prepare = self.root / "rfd3_scripts" / "prepare_campaign.py"
        protein = self.root / "rfd3_scripts" / "rfd3_protein_campaign.py"
        prepare.write_text("# prepare\n"); protein.write_text("# runner\n")
        base = {"target_kind": "protein", "target_structure": str(target), "target_sequence": "ACDEFG", "target_chains": ["B"], "source_binder_chain": "A", "lengths": [60], "sequence_model": "solublempnn", "extra_predictors": ["boltz"]}
        partial = plans.rfd3_plan({"project": "demo", "request": {**base, "design_mode": "partialDiffusion", "partial_t": 2.0, "infer_ori_strategy": "hotspots"}}, "partialDiffusion")
        normalized = partial["normalized_request"]["request"]
        self.assertEqual(normalized["partial_t"], 2.0)
        self.assertNotIn("infer_ori_strategy", normalized)
        with self.assertRaisesRegex(common.StudioError, "explicit motif_sites"):
            plans.rfd3_plan({"project": "demo", "request": {**base, "design_mode": "motifScaffolding", "motif_sites": {}}}, "motifScaffolding")
        motif = plans.rfd3_plan({"project": "demo", "request": {**base, "design_mode": "motifScaffolding", "motif_sites": {"A19": "CG,CE1,CZ"}}}, "motifScaffolding")
        self.assertEqual(motif["normalized_request"]["request"]["motif_sites"], {"A19": "CG,CE1,CZ"})

        denovo = {key: value for key, value in base.items() if key not in {"source_binder_chain"}}
        denovo.pop("lengths")
        simple = plans.rfd3_plan({"project": "demo", "request": {**denovo, "design_mode": "deNovo"}}, "deNovo")
        request = simple["normalized_request"]["request"]
        self.assertNotIn("contig", request)
        self.assertNotIn("component_id", request)
        self.assertEqual(request["sequence_model"], "solublempnn")
        self.assertEqual(request["binding_site_mode"], "surface_scan")
        self.assertEqual(request["hit_filters"]["minimum_ipsae_min"], 0.50)
        with self.assertRaisesRegex(common.StudioError, "Omit `contig`"):
            plans.rfd3_plan({"project": "demo", "request": {**denovo, "design_mode": "deNovo", "contig": "B1-236/0 45-75"}}, "deNovo")
        with self.assertRaisesRegex(common.StudioError, "silently disagree"):
            plans.rfd3_plan({"project": "demo", "request": {**denovo, "design_mode": "deNovo", "contig": "45-75,/0,B1-236"}}, "deNovo")

        targeted = plans.rfd3_plan({"project": "demo", "request": {
            **denovo, "design_mode": "deNovo",
            "conditions": {"B3": ["hotspot"]},
        }}, "deNovo")["normalized_request"]["request"]
        self.assertEqual(targeted["binding_site_mode"], "targeted_epitope")
        self.assertEqual(targeted["infer_ori_strategy"], "hotspots")
        patch = plans.rfd3_plan({"project": "demo", "request": {
            **denovo, "design_mode": "deNovo", "binding_site_mode": "surface_patch",
            "surface_patch_residues": ["B4", "B3", "B4"],
        }}, "deNovo")["normalized_request"]["request"]
        self.assertEqual(patch["surface_patch_residues"], ["B3", "B4"])
        self.assertNotIn("infer_ori_strategy", patch)
        with self.assertRaisesRegex(common.StudioError, "Target-centre ORI is unsafe"):
            plans.rfd3_plan({"project": "demo", "request": {
                **denovo, "design_mode": "deNovo", "infer_ori_strategy": "com",
            }}, "deNovo")

    def test_workflow_guide_prevents_transcript_routing_mistakes(self):
        guide = catalog.workflow_guide("rfd3_protein_binder")
        self.assertEqual(guide["defaults"]["sequence_model"], "solublempnn")
        self.assertEqual(guide["defaults"]["binding_site_mode"], "surface_scan")
        self.assertIn("Never use LASErMPNN", guide["rules"][1])
        self.assertIn("1-5 backbone", guide["long_campaign_rule"])
        self.assertTrue(any("Do not rank on iPTM alone" in rule for rule in guide["rules"]))

    def test_run_profile_can_read_complete_rfd3_results_with_legacy_provenance(self):
        run = self.root / "projects" / "demo" / "rfd3_runs" / "rfd3-results"
        (run / "config").mkdir(parents=True)
        (run / "analysis").mkdir()
        (run / "rfd3").mkdir()
        (run / "mpnn").mkdir()
        (run / "predictions" / "holo").mkdir(parents=True)
        (run / "predictions" / "apo").mkdir(parents=True)
        (run / "config" / "campaign.json").write_text("{}\n")
        (run / "analysis" / "top100.csv").write_text(
            "name,pdb,score,is_hit\ndesign_0001_0,predictions/holo/boltz_results/example.pdb,0.91,True\n"
        )
        (run / "rfd3" / "backbone_metrics.csv").write_text(
            "design,backbone_pdb,ca_valid_pct\ndesign_0001,rfd3/backbones/design_0001.pdb,100\n"
        )
        (run / "predictions" / "holo" / "prediction_metrics.csv").write_text(
            "name,pdb,iptm\ndesign_0001_0,predictions/holo/boltz_results/example.pdb,0.80\n"
        )
        (run / "predictions" / "apo" / "prediction_metrics.csv").write_text(
            "name,pdb,complex_plddt\ndesign_0001_0,predictions/apo/boltz_results/example.pdb,0.88\n"
        )
        (run / "mpnn" / "sequences.csv").write_text(
            "design,seq_index,sequence,backbone_pdb\ndesign_0001,0,AAAA,rfd3/backbones/design_0001.pdb\n"
        )
        (run / "rfd3" / "backbones").mkdir()
        (run / "rfd3" / "backbones" / "design_0001.pdb").write_text("ATOM\n")
        (run / "predictions" / "holo" / "boltz_results").mkdir()
        (run / "predictions" / "holo" / "boltz_results" / "example.pdb").write_text("ATOM\n")
        (run / "predictions" / "apo" / "boltz_results").mkdir()
        (run / "predictions" / "apo" / "boltz_results" / "example.pdb").write_text("ATOM\n")

        run_id = "demo/rfd3_runs/rfd3-results"
        record = catalog.run_status(run_id)
        self.assertIn("rfd3/backbone_metrics.csv", record["result_files"])
        self.assertIn("predictions/apo/prediction_metrics.csv", record["result_files"])

        ranked = catalog.query_results(run_id, "analysis/top100.csv", None, False, 10)
        self.assertEqual(ranked["rows"][0]["predictor"], "boltz")
        self.assertEqual(ranked["rows"][0]["prediction_context"], "complex")
        apo = catalog.query_results(run_id, "predictions/apo/prediction_metrics.csv", None, False, 10)
        self.assertEqual(apo["rows"][0]["predictor"], "boltz")
        self.assertEqual(apo["rows"][0]["prediction_context"], "binder_alone")
        backbones = catalog.query_results(run_id, "rfd3/backbone_metrics.csv", None, False, 10)
        self.assertEqual(backbones["rows"][0]["predictor"], "rfd3-mlx")
        self.assertEqual(backbones["rows"][0]["prediction_context"], "generated_backbone")

        overview = catalog.results_overview(run_id)
        self.assertEqual(overview["organization"], "RFdiffusion3 backbone -> MPNN derivative -> complex/binder-alone validation")
        self.assertEqual(len(overview["groups"]), 1)
        self.assertEqual(overview["groups"][0]["id"], "rfd3|design_0001")
        derivative = overview["groups"][0]["variants"][0]
        self.assertEqual(derivative["id"], "design_0001_0")
        self.assertEqual({item["role"] for item in derivative["artifacts"]}, {"complex_reprediction", "binder_alone"})
        self.assertTrue(derivative["is_hit"])

        module = importlib.import_module("server")
        run_tools = {tool["name"] for tool in module.MCPServer("run").dispatch({"method": "tools/list"})["tools"]}
        self.assertIn("system_detect", run_tools)
        self.assertIn("runs_list", run_tools)
        self.assertIn("results_query", run_tools)
        self.assertIn("results_overview", run_tools)

    def test_iterative_overview_keeps_cycles_artifacts_and_trajectory_together(self):
        run = self.root / "projects" / "demo" / "iterative_runs" / "organized"
        (run / "run_001" / "cycle_00").mkdir(parents=True)
        (run / "run_001" / "cycle_01").mkdir()
        post = run / "run_001" / "post_boltz" / "cycle_01"
        (post / "binder_alone").mkdir(parents=True)
        (run / "studio_run.json").write_text(json.dumps({"arguments": ["--predictor", "protenix-v2"]}))
        for relative in (
            "run_001/cycle_00/model.cif", "run_001/cycle_01/model.cif",
            "run_001/post_boltz/cycle_01/complex.cif",
            "run_001/post_boltz/cycle_01/binder_alone/binder.cif",
        ):
            (run / relative).write_text("data_test\n")
        (run / "run_001" / "metrics_per_cycle.csv").write_text(
            "cycle,iptm,complex_plddt,structure_path,binder_sequence\n"
            "0,0.2,0.5,run_001/cycle_00/model.cif,AAAA\n"
            "1,0.7,0.8,run_001/cycle_01/model.cif,AAAA\n"
        )
        (post / "post_metrics_row.csv").write_text(
            "run,cycle,predictor,iptm,ipsae_min,binder_plddt,complex_rmsd,binder_rmsd,structure_path,binder_structure_path,is_hit,failed_filters\n"
            "1,1,boltz,0.8,0.7,0.9,1.2,1.0,run_001/post_boltz/cycle_01/complex.cif,run_001/post_boltz/cycle_01/binder_alone/binder.cif,True,\n"
        )

        overview = catalog.results_overview("demo/iterative_runs/organized")
        self.assertEqual(overview["workflow"], "iterative")
        self.assertEqual(len(overview["groups"]), 1)
        group = overview["groups"][0]
        self.assertEqual([item["id"] for item in group["variants"]], ["cycle|0", "cycle|1"])
        self.assertEqual([item["id"] for item in group["trajectory"]["frames"]], ["cycle|0", "cycle|1"])
        self.assertEqual(group["trajectory"]["alignment"], "matching target-chain C-alpha atoms (chains B onward)")
        cycle_one = group["variants"][1]
        self.assertEqual({item["role"] for item in cycle_one["artifacts"]}, {
            "designed_complex", "complex_reprediction", "binder_alone"
        })
        self.assertTrue(cycle_one["is_hit"])
        status = catalog.run_status("demo/iterative_runs/organized")
        self.assertNotIn("comparison_scores_long.csv", status["result_files"])

        (run / "comparison_scores_long.csv").write_text(
            "stage,predictor,run,cycle,iptm,structure_path\n"
            "design,protenix-v2,1,0,0.2,run_001/cycle_00/model.cif\n"
        )
        status = catalog.run_status("demo/iterative_runs/organized")
        self.assertIn("comparison_scores_long.csv", status["result_files"])
        queried = catalog.query_results(
            "demo/iterative_runs/organized", "comparison_scores_long.csv", "iptm", False, 10
        )
        self.assertEqual(queried["distribution"]["count"], 1)

    def test_target_preparation_and_inspection_keep_explicit_msa_and_artifacts(self):
        target_plan = plans.target_prepare_plan({"project": "demo", "name": "target", "predictors": ["boltz"], "sequences": [{"id": "B", "sequence": "ACDEFG"}]})
        chain = target_plan["normalized_request"]["config"]["jobs"][0]["chains"][0]
        self.assertEqual(chain["msa"], "auto")
        self.assertEqual(target_plan["kind"], "target_prepare")

        python = self.root / "rfd3" / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nexec /usr/bin/python3 "$@"\n')
        python.chmod(0o755)
        inspector = self.root / "rfd3_scripts" / "inspect_target.py"
        inspector.write_text("import json; print(json.dumps({'kind':'protein','sites':[{'name':'B1'}],'chains':['B'],'warnings':[]}))\n")
        structure = self.root / "projects" / "demo" / "inputs" / "target.pdb"
        structure.write_text("ATOM\n")
        inspected = target_inspection.inspect_target({"kind": "protein", "structure": str(structure), "chain": "B"})
        self.assertEqual(inspected["chains"], ["B"])
        self.assertEqual(len(inspected["input_artifact"]["sha256"]), 64)
        with self.assertRaisesRegex(common.StudioError, "outside"):
            common.import_artifact("/etc/passwd")

    def test_configuration_writers_preserve_unrelated_entries(self):
        project = self.root / "client-project"
        (project / ".codex").mkdir(parents=True)
        (project / ".codex" / "config.toml").write_text('model = "gpt-test"\n')
        (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "true"}}}))
        subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "both", "--scope", "project", "--project-root", str(project), "--write"], check=True, env=os.environ, capture_output=True, text=True)
        codex = (project / ".codex" / "config.toml").read_text()
        self.assertIn('model = "gpt-test"', codex)
        self.assertIn("mcp_servers.iproteinstudio-read", codex)
        self.assertNotIn("iproteinstudio-admin", codex)
        claude = json.loads((project / ".mcp.json").read_text())
        self.assertIn("other", claude["mcpServers"])
        self.assertIn("iproteinstudio-run", claude["mcpServers"])
        os.environ["IPROTEINSTUDIO_ENABLE_ADMIN_MCP"] = "1"
        try:
            subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "both", "--scope", "project", "--project-root", str(project), "--profiles", "read,run,admin", "--write"], check=True, env=os.environ, capture_output=True, text=True)
        finally:
            os.environ.pop("IPROTEINSTUDIO_ENABLE_ADMIN_MCP", None)
        codex = (project / ".codex" / "config.toml").read_text()
        self.assertIn('IPROTEINSTUDIO_ENABLE_ADMIN_MCP = "1"', codex)
        claude = json.loads((project / ".mcp.json").read_text())
        self.assertEqual(claude["mcpServers"]["iproteinstudio-admin"]["env"]["IPROTEINSTUDIO_ENABLE_ADMIN_MCP"], "1")

    def test_clickable_desktop_configuration_status_and_removal_are_scoped(self):
        project = self.root / "desktop-project"
        project.mkdir()
        codex_config = project / ".codex" / "config.toml"
        codex_config.parent.mkdir()
        codex_config.write_text('model = "gpt-test"\n')
        desktop_config = self.root / "claude_desktop_config.json"
        desktop_config.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "true"}}}))
        os.environ["IPROTEINSTUDIO_CLAUDE_DESKTOP_CONFIG"] = str(desktop_config)

        subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "codex", "--scope", "project", "--project-root", str(project), "--profiles", "read,run", "--write"], check=True, env=os.environ, capture_output=True, text=True)
        subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "claude-desktop", "--scope", "user", "--profiles", "read", "--write"], check=True, env=os.environ, capture_output=True, text=True)
        status = subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "claude-desktop", "--scope", "user", "--status"], check=True, env=os.environ, capture_output=True, text=True)
        report = json.loads(status.stdout)
        self.assertEqual(report["claude_desktop"]["profiles"], ["read"])
        self.assertNotIn("type", json.loads(desktop_config.read_text())["mcpServers"]["iproteinstudio-read"])
        self.assertEqual(codex_config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(desktop_config.stat().st_mode & 0o777, 0o600)

        subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "codex", "--scope", "project", "--project-root", str(project), "--remove", "--write"], check=True, env=os.environ, capture_output=True, text=True)
        subprocess.run(["/usr/bin/python3", str(MCP / "configure.py"), "--client", "claude-desktop", "--scope", "user", "--remove", "--write"], check=True, env=os.environ, capture_output=True, text=True)
        self.assertEqual(codex_config.read_text(), 'model = "gpt-test"\n')
        desktop = json.loads(desktop_config.read_text())
        self.assertEqual(desktop["theme"], "dark")
        self.assertEqual(set(desktop["mcpServers"]), {"other"})

    def test_studioctl_doctor_loads_every_profile_and_versioned_schema(self):
        completed = subprocess.run(
            ["/usr/bin/python3", str(MCP / "studioctl.py"), "doctor"],
            check=True, capture_output=True, text=True, env=os.environ,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(set(report["profiles"]), {"read", "run", "admin"})
        self.assertIn("target-prepare-v1.json", report["schemas"])

    def test_remote_gateway_is_loopback_capability_authenticated_and_stoppable(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        launched = subprocess.run(
            ["/usr/bin/python3", str(MCP / "remote_gateway.py"), "start", "--profile", "read", "--port", str(port)],
            check=True, capture_output=True, text=True, env=os.environ,
        )
        state = json.loads(launched.stdout)
        self.assertTrue(state["running"])
        self.assertEqual(state["bind"], "127.0.0.1")
        gateway_pid = state["pid"]
        with self.assertRaises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/mcp/not-the-token", data=b"{}", timeout=2)
        self.assertEqual(unauthorized.exception.code, 401)
        request = urllib.request.Request(
            state["local_endpoint"],
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        names = {tool["name"] for tool in payload["result"]["tools"]}
        self.assertIn("results_query", names)
        self.assertNotIn("job_start", names)
        stopped = subprocess.run(
            ["/usr/bin/python3", str(MCP / "remote_gateway.py"), "stop"],
            check=True, capture_output=True, text=True, env=os.environ,
        )
        self.assertFalse(json.loads(stopped.stdout)["running"])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and common.process_alive(gateway_pid):
            time.sleep(0.05)
        self.assertFalse(common.process_alive(gateway_pid))

        run_launch = subprocess.run(
            ["/usr/bin/python3", str(MCP / "remote_gateway.py"), "start", "--profile", "run", "--port", str(port)],
            check=True, capture_output=True, text=True, env=os.environ,
        )
        run_state = json.loads(run_launch.stdout)
        self.assertNotEqual(run_state["local_endpoint"], state["local_endpoint"])
        request = urllib.request.Request(
            run_state["local_endpoint"],
            data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            run_payload = json.loads(response.read())
        run_names = {tool["name"] for tool in run_payload["result"]["tools"]}
        self.assertIn("job_start", run_names)
        self.assertNotIn("engine_install_plan", run_names)
        subprocess.run(
            ["/usr/bin/python3", str(MCP / "remote_gateway.py"), "stop"],
            check=True, capture_output=True, text=True, env=os.environ,
        )


if __name__ == "__main__":
    unittest.main()
