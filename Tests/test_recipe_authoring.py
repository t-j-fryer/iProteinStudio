"""CPU-only authoring/stdio tests; never call a planner or a job tool."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "Sources/iProteinStudio/Resources/pipeline/mcp"
sys.path.insert(0, str(MCP))
from iprotein_mcp.recipes import example, recipe_catalog, recipe_check, recipe_compare
from iprotein_mcp.common import StudioError


class RecipeAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.recipe = example("protein_binder")

    def assertIssue(self, code):
        result = recipe_check(self.recipe)
        self.assertFalse(result["valid"])
        self.assertIn(code, [i["code"] for i in result["issues"]])
        self.assertFalse(result["executable"])

    def test_catalogue_roundtrip_and_no_mutation(self):
        for goal, recipe in recipe_catalog()["examples"].items():
            with self.subTest(goal=goal):
                before = copy.deepcopy(recipe)
                a = recipe_check(recipe)
                b = recipe_check(json.loads(json.dumps(recipe)))
                self.assertTrue(a["valid"], a)
                self.assertEqual(a["recipe_sha256"], b["recipe_sha256"])
                self.assertEqual(recipe, before)
                self.assertFalse(a["executable"])
                self.assertNotIn("plan_id", a)
                self.assertEqual(len(a["edges"]), len(recipe["stages"])-1)

    def test_sequence_required_before_prediction(self):
        del self.recipe["stages"][2]
        self.assertIssue("connection")

    def test_ligand_designer_rejected_for_protein(self):
        self.recipe["stages"][2]["module"] = "lasermpnn"
        self.assertIssue("goal")

    def test_ligand_recipe_cannot_claim_protein_inputs(self):
        self.recipe = example("ligand_binder")
        self.recipe["input"]["kind"] = "protein"
        self.assertIssue("target_kind")

    def test_unknown_module_fails_no_substitution(self):
        self.recipe["stages"][2]["module"] = "new-engine"
        before = copy.deepcopy(self.recipe)
        self.assertIssue("unknown_module")
        self.assertEqual(before, self.recipe)

    def test_duplicate_ids_rejected(self):
        self.recipe["stages"][1]["id"] = "s1"
        self.assertIssue("duplicate_id")

    def test_reordered_stages_rejected(self):
        self.recipe["stages"][1:3] = reversed(self.recipe["stages"][1:3])
        self.assertIssue("connection")

    def test_bounded_loop_and_digest(self):
        before = recipe_check(self.recipe)["recipe_sha256"]
        self.recipe["stages"].insert(4, dict(id="loop", module="hunter"))
        self.assertIssue("loop")
        self.recipe["budget"]["refinement_cycles"] = 2
        result = recipe_check(self.recipe)
        self.assertTrue(result["valid"])
        self.assertNotEqual(before, result["recipe_sha256"])
        self.recipe["budget"]["refinement_cycles"] = 6
        self.assertIssue("schema")

    def test_disabled_checks_rejected(self):
        for field in ["independent", "binder_alone"]:
            self.recipe = example("protein_binder")
            self.recipe["assessment"][field] = False
            self.assertIssue("assessment")

    def test_missing_assessment_stage_rejected(self):
        del self.recipe["stages"][-2]
        self.assertIssue("connection")

    def test_schema_and_version_strict(self):
        for path, value in [("schema_version", 2), ("schema_version", True), ("catalog_version", "future"), ("extra", 0)]:
            self.recipe = example("protein_binder")
            self.recipe[path] = value
            self.assertIssue("schema")

    def test_input_scope_and_msa_strict(self):
        self.recipe["input"]["source"] = "/a/real/input.pdb"
        self.assertIssue("schema")
        self.recipe = example("protein_binder")
        self.recipe["input"]["target_msa"] = "not_applicable"
        self.assertIssue("msa")
        self.recipe = example("protein_binder")
        self.recipe["input"]["binder_msa"] = "auto"
        self.assertIssue("schema")

    def test_large_campaign_and_noninteger_budget_rejected(self):
        for value in [11, 0, True, 2.5, float("nan")]:
            self.recipe["budget"]["starts"] = value
            self.assertIssue("schema")

    def test_name_length_rejected(self):
        self.recipe["name"] = "x" * 121
        self.assertIssue("length")

    def test_save_is_terminal(self):
        self.recipe["stages"].append(dict(id="later", module="hunter"))
        self.recipe["budget"]["refinement_cycles"] = 1
        self.assertIssue("order")

    def test_matched_strategy_comparison(self):
        variant = copy.deepcopy(self.recipe)
        variant["stages"][2]["module"] = "proteinmpnn"
        result = recipe_compare(self.recipe, variant)
        self.assertTrue(result["comparison_ready_for_review"])
        self.assertEqual([d["path"] for d in result["differences"]], ["stages[2].module"])
        self.assertFalse(result["executable"])

    def test_changed_budgets_not_matched(self):
        variant = copy.deepcopy(self.recipe)
        variant["budget"]["starts"] = 4
        result = recipe_compare(self.recipe, variant)
        self.assertFalse(result["matched_controls"])
        self.assertFalse(result["comparison_ready_for_review"])
        self.assertEqual(result["changed_controls"], ["budget"])

    def test_names_and_ids_are_not_scientific_changes(self):
        variant = copy.deepcopy(self.recipe)
        variant["name"] = "Renamed"
        variant["stages"][0]["id"] = "input"
        result = recipe_compare(self.recipe, variant)
        self.assertEqual(result["differences"], [])
        self.assertFalse(result["comparison_ready_for_review"])

    def test_runtime_claim_not_inferred_from_engine_change(self):
        variant = copy.deepcopy(self.recipe)
        variant["stages"][3]["module"] = "protenix"
        self.assertFalse(recipe_compare(self.recipe, variant, "runtime")["comparison_ready_for_review"])

    def test_invalid_comparison_fails(self):
        variant = copy.deepcopy(self.recipe)
        variant["stages"].pop()
        with self.assertRaises(StudioError):
            recipe_compare(self.recipe, variant)

    def test_stdio_read_profile_exposes_authoring_not_execution(self):
        with tempfile.TemporaryDirectory() as root:
            env = dict(os.environ, IPROTEINSTUDIO_TEST_SUPPORT_ROOT=root,
                       IPROTEINSTUDIO_AGENT_ROOT=str(Path(root)/"agent"), PYTHONDONTWRITEBYTECODE="1")
            messages = [
                {"jsonrpc":"2.0", "id":1, "method":"tools/list"},
                {"jsonrpc":"2.0", "id":2, "method":"tools/call", "params":{"name":"recipe_check", "arguments":{"recipe":self.recipe}}},
                {"jsonrpc":"2.0", "id":3, "method":"tools/call", "params":{"name":"job_start", "arguments":{"plan_id":"not-a-plan", "plan_sha256":"not-a-digest"}}},
                {"jsonrpc":"2.0", "id":4, "method":"tools/call", "params":{"name":"workflow_guide", "arguments":{"workflow":"rfd3_protein_binder"}}},
            ]
            result = subprocess.run([sys.executable, str(MCP/"server.py"), "--profile", "read"],
                input="\n".join(json.dumps(m) for m in messages)+"\n", text=True, capture_output=True,
                env=env, check=True, timeout=15)
            replies = [json.loads(line)["result"] for line in result.stdout.splitlines()]
            tools = {t["name"]:t for t in replies[0]["tools"]}
            for name in ["recipe_catalog", "recipe_check", "recipe_compare"]:
                self.assertTrue(tools[name]["annotations"]["readOnlyHint"])
                self.assertFalse(tools[name]["annotations"]["openWorldHint"])
            self.assertNotIn("job_start", tools)
            self.assertTrue(replies[1]["structuredContent"]["valid"])
            self.assertTrue(replies[2]["isError"])
            self.assertEqual(replies[3]["structuredContent"]["workflow"], "rfd3_protein_binder")
            # The bridge creates empty storage folders while recording read audits.
            self.assertEqual(list((Path(root)/"agent/jobs").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
