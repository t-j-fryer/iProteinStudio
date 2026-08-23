#!/usr/bin/env python3
"""Contract tests for Studio's RFdiffusion3 and plain-prediction helpers."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RFD3 = ROOT / "Sources/iProteinStudio/Resources/rfd3"
OVERLAY = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay/scripts"
sys.path.insert(0, str(OVERLAY))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def pdb_atom(serial: int, name: str, resname: str, chain: str, resnum: int,
             x: float, y: float, z: float, element: str) -> str:
    return (f"ATOM  {serial:5d} {name:^4s} {resname:>3s} {chain}{resnum:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00          {element:>2s}")


def main() -> None:
    run_mpnn = load("run_mpnn_contract", OVERLAY / "run_mpnn.py")
    prepare_inputs = load("prepare_inputs_contract", OVERLAY / "prepare_predictor_inputs.py")
    score = load("score_contract", OVERLAY / "score_and_select.py")
    predict = load("predict_contract", RFD3 / "predict_batch.py")
    prepare = load("prepare_contract", RFD3 / "prepare_campaign.py")
    protein_campaign = load("protein_campaign_contract", RFD3 / "rfd3_protein_campaign.py")
    openfold = load("openfold_contract", OVERLAY / "openfold_predict_one.py")
    pipeline_scripts = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts"
    sys.path.insert(0, str(pipeline_scripts))
    ipsae = load("ipsae_contract", pipeline_scripts / "ipsae_score.py")
    protenix = load("protenix_contract", pipeline_scripts / "protenix_predict.py")
    intellifold = load("intellifold_mps_contract", pipeline_scripts / "intellifold_predict.py")

    with tempfile.TemporaryDirectory(prefix="iproteinstudio-workflow-contract-") as raw:
        root = Path(raw)

        # Every overlay helper must be callable from a clean source checkout.
        # Root detection belongs after argument parsing; otherwise even --help
        # used to fail before an explicit --nanohunter-root could be honored.
        for helper in ("prepare_boltz_yaml.py", "run_mpnn.py", "compute_rmsd.py",
                       "run_lasermpnn.py", "run_boltz_affinity.py", "run_predictors.py"):
            subprocess.run([sys.executable, str(OVERLAY / helper), "--help"],
                           check=True, capture_output=True, text=True)

        fasta = root / "multi.fa"
        fasta.write_text(
            ">native\nAAAAA\n"
            ">design_1, overall_confidence=0.8\nCCCCC\n"
            ">design_2, overall_confidence=0.7\nDDDDD\n"
        )
        designs = run_mpnn.parse_fasta(fasta)
        expect(len(designs) == 2 and designs[1][0] == "DDDDD",
               "MPNN multi-sequence FASTA parsing lost a designed record")

        row1 = {"design": "design_001", "seq_index": "1"}
        row2 = {"design": "design_001", "seq_index": "2"}
        expect(prepare_inputs.prediction_name(row1) != prepare_inputs.prediction_name(row2),
               "protein RFdiffusion3 sequence variants still overwrite one YAML")
        expect(score.prediction_name(row2) == prepare_inputs.prediction_name(row2),
               "protein scoring and input naming disagree")

        a3m = root / "target.a3m"
        a3m.write_text(">query\nACDEFG\n>homologue\nACDEFG\n")
        expect(predict.valid_a3m(a3m, "ACDEFG"), "valid cached MSA was rejected")
        a3m.write_text(">query\nACDEFG\n")
        expect(not predict.valid_a3m(a3m, "ACDEFG"),
               "query-only MSA was accepted as a real alignment")

        external_msa = root / "external" / "cached.a3m"
        external_msa.parent.mkdir()
        external_msa.write_text(">query\nACDEFG\n>homologue\nACDEFG\n")
        run_inputs = root / "run" / "inputs"
        materialized = predict.materialize_msas({"digest": str(external_msa)}, run_inputs)
        durable_msa = Path(materialized["digest"])
        expect(durable_msa.parent.resolve() == (run_inputs / "msas").resolve()
               and durable_msa.read_bytes() == external_msa.read_bytes(),
               "saved prediction input still depends on an external MSA path")

        # OpenFold's raw-MSA parser filters on source basename even though its
        # public query format accepts an arbitrary path. The adapter must retain
        # the cached alignment's bytes while giving its private copy a name the
        # upstream parser recognizes.
        cached = root / "content-addressed-msa.a3m"
        cached.write_text(">query\nACDEFG\n>homologue\nACDEFG\n")
        openfold_query = root / "openfold-query.json"
        openfold_query.write_text(json.dumps({
            "queries": {"one": {"chains": [{
                "chain_ids": ["A"], "main_msa_file_paths": [str(cached)]
            }]}}
        }))
        openfold.normalize_openfold_msa_paths(openfold_query, root / "normalized")
        normalized_path = Path(json.loads(openfold_query.read_text())["queries"]
                               ["one"]["chains"][0]["main_msa_file_paths"][0])
        expect(normalized_path.name == "colabfold_main.a3m",
               "OpenFold cached MSA did not receive its required parser basename")
        expect(normalized_path.read_bytes() == cached.read_bytes(),
               "OpenFold MSA normalization changed the alignment contents")

        # `msa: empty` is an explicit scientific choice, not a cache miss.
        # OpenFold must not turn it back into a live MMseqs2 request.  A mixed
        # complex may still use a real alignment for another chain.
        openfold_builder = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/openfold_query_json.py"
        single_yaml = root / "single-sequence.yaml"
        single_yaml.write_text(
            "sequences:\n"
            "  - protein:\n"
            "      id: A\n"
            "      sequence: ACDEFG\n"
            "      msa: empty\n"
        )
        single_json = root / "single-sequence.json"
        built = subprocess.run([
            sys.executable, str(openfold_builder), str(single_yaml), "ACDEFG",
            "single", str(single_json), "", "", "42",
        ], check=True, capture_output=True, text=True)
        single_payload = json.loads(single_json.read_text())["queries"]["single"]
        expect(built.stdout.strip() == "false" and not single_payload["use_msas"],
               "OpenFold single-sequence policy still requested the MSA server")
        expect("main_msa_file_paths" not in single_payload["chains"][0],
               "OpenFold single-sequence policy invented an alignment")

        mixed_yaml = root / "mixed-msa.yaml"
        mixed_yaml.write_text(
            "sequences:\n"
            "  - protein:\n"
            "      id: A\n"
            "      sequence: ACDEFG\n"
            "      msa: empty\n"
            "  - protein:\n"
            "      id: B\n"
            "      sequence: HIKLMN\n"
            f"      msa: {cached}\n"
        )
        mixed_json = root / "mixed-msa.json"
        built = subprocess.run([
            sys.executable, str(openfold_builder), str(mixed_yaml), "ACDEFG",
            "mixed", str(mixed_json), "", "", "42",
        ], check=True, capture_output=True, text=True)
        mixed_payload = json.loads(mixed_json.read_text())["queries"]["mixed"]
        expect(built.stdout.strip() == "false" and mixed_payload["use_msas"],
               "OpenFold mixed-chain policy did not retain the real alignment")
        expect("main_msa_file_paths" not in mixed_payload["chains"][0]
               and mixed_payload["chains"][1]["main_msa_file_paths"] == [str(cached)],
               "OpenFold mixed-chain MSA policy crossed chain boundaries")

        runner_source = (ROOT / "Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh").read_text()
        expect('scripts/openfold_query_json.py' in runner_source
               and '\"use_msas\": True' not in runner_source,
               "iterative runner drifted from the shared OpenFold MSA policy")

        # Protenix has one process-wide MSA switch. A fully explicit-empty job
        # must force it off; a mixed job must retain the target alignment while
        # representing the empty binder with a query-only A3M. Neither case may
        # give upstream permission to search online.
        no_msa_job, no_msa_chains, no_msa_real = protenix.convert_yaml(single_yaml)
        expect(not no_msa_real and len(no_msa_chains) == 1
               and "unpairedMsaPath" not in no_msa_job["sequences"][0]["proteinChain"],
               "Protenix did not retain the explicit single-sequence policy")
        no_msa_command = protenix.protenix_command(
            Path("protenix"), root / "single.json", root / "px", "protenix-v2",
            "42", 2, False,
        )
        expect(no_msa_command[no_msa_command.index("--use_msa") + 1] == "False",
               "Protenix explicit-empty job still permits an MSA-server request")
        expect(no_msa_command[no_msa_command.index("--need_atom_confidence") + 1] == "True",
               "Protenix did not request the token PAE needed for ipSAE")

        mixed_job, mixed_empty, mixed_real = protenix.convert_yaml(mixed_yaml)
        converted = [(mixed_job, mixed_empty, mixed_real)]
        protenix.materialize_single_sequence_msas(converted, root / "px-msas")
        mixed_proteins = [entry["proteinChain"] for entry in mixed_job["sequences"]]
        binder_msa = Path(mixed_proteins[0]["unpairedMsaPath"])
        expect(mixed_real and binder_msa.read_text() == ">query\nACDEFG\n"
               and mixed_proteins[1]["unpairedMsaPath"] == str(cached.resolve()),
               "Protenix mixed-chain policy lost the real MSA or searched the empty chain")

        # Dunbrack v4 d0res semantics are directional. Studio persists both
        # directions and exposes their conservative minimum.
        pae = ipsae.np.array([
            [0, 0, 1, 20],
            [0, 0, 2, 2],
            [4, 20, 0, 0],
            [4, 4, 0, 0],
        ], dtype=float)
        values = ipsae.calculate_ipsae(pae, ["A", "A", "B", "B"], ["A", "B"])
        expect(abs(values["ipsae_directional"]["A>B"] - 0.5) < 1e-12,
               "ipSAE A>B departed from the Dunbrack d0res equation")
        expect(abs(values["ipsae_directional"]["B>A"] - (1 / 17)) < 1e-12
               and abs(values["ipsae_min"] - (1 / 17)) < 1e-12,
               "ipSAE(min) was not the smaller directional score")

        boltz_score_root = root / "boltz-score"
        boltz_score_root.mkdir()
        boltz_pae = ipsae.np.full((12, 12), 20.0)
        ipsae.np.fill_diagonal(boltz_pae, 0.0)
        boltz_pae[:6, 6:] = 1.0
        boltz_pae[6:, :6] = 4.0
        ipsae.np.savez(boltz_score_root / "pae_mixed-msa_model_0.npz", pae=boltz_pae)
        boltz_confidence = boltz_score_root / "confidence_mixed-msa_model_0.json"
        boltz_confidence.write_text('{"iptm": 0.7}\n')
        expect(ipsae.annotate_boltz(mixed_yaml, boltz_score_root) == 1,
               "Boltz multimer PAE was not annotated")
        expect("ipsae_min" in json.loads(boltz_confidence.read_text()),
               "Boltz confidence JSON did not retain ipSAE(min)")

        protenix_score_root = root / "protenix-score"
        protenix_predictions = protenix_score_root / mixed_job["name"] / "seed_42" / "predictions"
        protenix_predictions.mkdir(parents=True)
        protenix_full = protenix_predictions / f"{mixed_job['name']}_full_data_sample_0.json"
        protenix_summary = protenix_predictions / f"{mixed_job['name']}_summary_confidence_sample_0.json"
        protenix_full.write_text(json.dumps({
            "token_pair_pae": boltz_pae.tolist(),
            "token_asym_id": [0] * 6 + [1] * 6,
        }))
        protenix_summary.write_text('{"iptm": 0.7}\n')
        expect(ipsae.annotate_protenix(protenix_score_root, [mixed_job]) == 1,
               "Protenix full confidence was not scored")
        expect("ipsae_min" in json.loads(protenix_summary.read_text()),
               "Protenix summary did not receive ipSAE(min)")

        # The strict IntelliFold wrapper is testable without importing PyTorch.
        # Validate its exact seed/sample accounting against a synthetic output.
        if_inputs = root / "if-inputs"
        if_inputs.mkdir()
        (if_inputs / "one.yaml").write_text("sequences: []\n")
        if_job = root / "if-results" / "if-inputs" / "predictions" / "one"
        if_job.mkdir(parents=True)
        for sample in range(2):
            stem = f"one_seed-42_sample-{sample}"
            (if_job / f"{stem}.cif").write_text("data_test\n")
            (if_job / f"{stem}_summary_confidences.json").write_text("{}\n")
            (if_job / f"{stem}_confidences.json").write_text(json.dumps({
                "pae": [[0.0]], "token_chain_ids": ["A"],
            }))
        intellifold.verify_outputs([
            str(if_inputs), "--out_dir", str(root / "if-results"),
            "--seed", "42", "--num_diffusion_samples", "2",
        ])
        (if_job / "one_seed-42_sample-1.cif").unlink()
        try:
            intellifold.verify_outputs([
                str(if_inputs), "--out_dir", str(root / "if-results"),
                "--seed", "42", "--num_diffusion_samples", "2",
            ])
        except SystemExit:
            pass
        else:
            raise AssertionError("IntelliFold missing output was silently accepted")
        expect(intellifold.STRICT_ACCELERATE_VERSION == "1.1.1"
               and intellifold.STRICT_TORCH_VERSION == "2.6.0",
               "IntelliFold strict launcher drifted from the installed version pins")

        try:
            predict.validate_config({"predictors": ["boltz"]}, [
                {"name": "../escape", "chains": [
                    {"id": "A", "kind": "protein", "sequence": "ACDEFG"}
                ]}
            ])
        except SystemExit:
            pass
        else:
            raise AssertionError("unsafe prediction job name was accepted as an output path")

        output = root / "chunk"
        (output / "one").mkdir(parents=True)
        (output / "one" / "model.cif").write_text("data_test\n")
        marker = output / "chunk_complete.json"
        marker.write_text(json.dumps({"predictor": "openfold-3-mlx", "jobs": ["one"]}))
        expect(predict.completed_chunk(marker, ["one"], output),
               "completed prediction checkpoint was not reusable")
        expect(not predict.completed_chunk(marker, ["missing"], output),
               "a different job's structure satisfied the retry checkpoint")

        # Sampling settings must lower to each native CLI without changing the
        # established default when the override is zero.
        command_log = []
        environment_log = []
        real_popen = predict.subprocess.Popen

        class FakePopen:
            def __init__(self, command, **kwargs):
                command_log.append(command)
                environment_log.append(kwargs.get("env", {}))

        predict.subprocess.Popen = FakePopen
        try:
            one_yaml = root / "one.yaml"
            one_yaml.write_text("sequences: []\n")
            cfg = {"seed": 42, "num_seeds": 3, "diffusion_samples": 2,
                   "intellifold_model": "v2-flash"}
            predict.run_directory_batch("intellifold", [one_yaml], root / "if-out",
                                        root, {}, cfg, root / "if.log")
            predict.run_directory_batch("boltz", [one_yaml], root / "boltz-out",
                                        root, {}, cfg, root / "boltz.log")
            predict.run_directory_batch("protenix-v2", [one_yaml], root / "px-out",
                                        root, {}, cfg, root / "px.log")
            predict.run_single("openfold-3-mlx", one_yaml, root / "openfold-out", root,
                               {}, root / "openfold.log", cfg)
        finally:
            predict.subprocess.Popen = real_popen

        intellifold_cmd, boltz_cmd, protenix_cmd, openfold_cmd = command_log
        expect(intellifold_cmd[intellifold_cmd.index("--seed") + 1] == "42,43,44",
               "IntelliFold did not receive the requested independent seeds")
        expect(intellifold_cmd[1].endswith("scripts/intellifold_predict.py")
               and environment_log[0].get("PYTORCH_ENABLE_MPS_FALLBACK") == "0",
               "plain prediction bypassed the strict IntelliFold MPS launcher")
        expect(intellifold_cmd[intellifold_cmd.index("--num_diffusion_samples") + 1] == "2",
               "IntelliFold did not receive the diffusion-sample override")
        expect(boltz_cmd[boltz_cmd.index("--seed") + 1] == "42"
               and boltz_cmd[boltz_cmd.index("--diffusion_samples") + 1] == "2",
               "Boltz seed/diffusion settings were lowered incorrectly")
        expect(protenix_cmd[protenix_cmd.index("--model") + 1] == "v2"
               and protenix_cmd[protenix_cmd.index("--seeds") + 1] == "42,43,44"
               and protenix_cmd[protenix_cmd.index("--samples") + 1] == "2",
               "Protenix model/seed/diffusion settings were lowered incorrectly")
        expect(openfold_cmd[openfold_cmd.index("--num-seeds") + 1] == "3"
               and openfold_cmd[openfold_cmd.index("--diffusion-samples") + 1] == "2",
               "OpenFold sampling controls did not reach its adapter")

        # Protein design ranking remains the established mean iPTM while the
        # conservative interface metric survives per engine and in aggregate.
        scoring_dir = root / "protein-scores"
        score.score_proteins([
            {"design": "d1", "predictor": "boltz", "exit_code": "0",
             "structure": "/tmp/boltz.cif", "iptm": "0.8", "ipsae_min": "0.6"},
            {"design": "d1", "predictor": "intellifold", "exit_code": "0",
             "structure": "/tmp/if.cif", "iptm": "0.6", "ipsae_min": "0.4"},
        ], SimpleNamespace(
            predictors="boltz,intellifold", sequences=None, require_top_n=False,
            top_n=100, output=scoring_dir,
        ))
        scored = json.loads((scoring_dir / "top100_manifest.json").read_text())[0]
        expect(abs(scored["score"] - 0.7) < 1e-12
               and abs(scored["mean_ipsae_min"] - 0.5) < 1e-12
               and abs(scored["min_ipsae_min"] - 0.4) < 1e-12,
               "protein design outputs lost cross-engine ipSAE(min)")

        overlay_if_command, overlay_if_env = load(
            "run_predictors_contract", OVERLAY / "run_predictors.py"
        ).command_for("intellifold", one_yaml, root / "overlay-if", root, "v2-flash")
        expect(overlay_if_command[1].endswith("scripts/intellifold_predict.py")
               and overlay_if_env.get("PYTORCH_ENABLE_MPS_FALLBACK") == "0"
               and 'INTELLIFOLD_RUNNER="${REPO_ROOT}/scripts/intellifold_predict.py"'
               in runner_source,
               "a design workflow bypassed the strict IntelliFold MPS launcher")

        expect(protein_campaign.verification_predictors(
            {"extra_predictors": ["protenix-v2"]}) == ["protenix-v2"],
            "protein RFdiffusion3 campaign rejected Protenix v2")
        try:
            protein_campaign.verification_predictors(
                {"extra_predictors": ["protenix-v2", "protenix-mini"]})
        except SystemExit as exc:
            expect("one model family" in str(exc),
                   "same-family Protenix validation was not actionable")
        else:
            raise AssertionError("Protenix Mini was accepted as an independent check of v2")

        for retired in ("alphafold3", "intellifold-jax"):
            try:
                predict.validate_config({"predictors": [retired]}, [{
                    "name": "one", "chains": [
                        {"id": "A", "kind": "protein", "sequence": "ACDEFG"}
                    ]
                }])
            except SystemExit:
                pass
            else:
                raise AssertionError(f"retired predictor {retired} passed validation")

            campaign_request = {
                "target_kind": "protein", "lengths": [65], "num_backbones": 1,
                "batch_size": 1, "queues_per_bin": 1, "timesteps": 1,
                "sequences_per_backbone": 1, "top_n": 1,
                "extra_predictors": [retired],
            }
            captured = io.StringIO()
            try:
                with contextlib.redirect_stdout(captured):
                    prepare.validate_request(campaign_request)
            except SystemExit:
                expect("Retired" in captured.getvalue(),
                       f"campaign-preparation retirement for {retired} was not actionable")
            else:
                raise AssertionError(f"retired campaign checker {retired} passed validation")

            try:
                protein_campaign.verification_predictors(
                    {"extra_predictors": [retired]})
            except SystemExit as exc:
                expect("Retired" in str(exc),
                       f"protein-campaign retirement for {retired} was not actionable")
            else:
                raise AssertionError(f"retired protein checker {retired} passed validation")

            rejected = subprocess.run([
                sys.executable, str(OVERLAY / "run_predictors.py"),
                "--inputs", str(root), "--output", str(root / "rejected"),
                "--predictors", retired, "--nanohunter-root", str(root),
            ], capture_output=True, text=True)
            expect(rejected.returncode != 0 and "retired" in rejected.stderr.lower(),
                   f"predictor overlay did not reject {retired} clearly")

        try:
            predict.validate_config({"predictors": ["boltz"], "num_seeds": 0}, [
                {"name": "one", "chains": [
                    {"id": "A", "kind": "protein", "sequence": "ACDEFG"}
                ]}
            ])
        except SystemExit:
            pass
        else:
            raise AssertionError("invalid prediction seed count reached a backend")

        sequence_csv = root / "sequences.csv"
        sequence_csv.write_text("design,seq_index,sequence\ndesign_001,1,AAAAA\n")
        yaml_out = root / "yaml"
        subprocess.run([
            sys.executable, str(OVERLAY / "prepare_boltz_yaml.py"),
            "--sequences", str(sequence_csv), "--output", str(yaml_out),
            "--mode", "holo", "--smiles", "CCO", "--no-affinity",
            "--nanohunter-root", str(root),
        ], check=True, capture_output=True, text=True)
        generated = next(yaml_out.glob("*.yaml")).read_text()
        expect("affinity:" not in generated,
               "disabling P(bind) still wrote the Boltz affinity property")

        pdb = root / "target.pdb"
        pdb.write_text("\n".join([
            pdb_atom(1, "CA", "ALA", "B", 1, 0, 0, 0, "C"),
            pdb_atom(2, "CA", "GLY", "B", 2, 2, 0, 0, "C"),
            "END",
        ]) + "\n")
        inspected = subprocess.run([
            sys.executable, str(RFD3 / "inspect_target.py"), "--kind", "protein",
            "--structure", str(pdb), "--chain", "B",
        ], check=True, capture_output=True, text=True)
        payload = json.loads(inspected.stdout.splitlines()[-1])
        expect(payload.get("sequence") == "AG", "protein inspector did not recover chain sequence")

        source = root / "input.fasta"
        source.write_text(">one\nACDEFG\n")
        parsed = subprocess.run([
            sys.executable, str(RFD3 / "parse_sequences.py"), str(source),
            "--mode", "shared", "--partner", "AAAAA", "--partner-smiles", "CCO",
        ], capture_output=True, text=True)
        expect(parsed.returncode != 0 and "either a protein partner" in parsed.stdout,
               "ambiguous shared partner input was silently accepted")

    print("PASS workflow pipeline contracts")


if __name__ == "__main__":
    main()
