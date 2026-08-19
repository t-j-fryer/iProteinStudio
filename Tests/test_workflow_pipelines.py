#!/usr/bin/env python3
"""Contract tests for Studio's RFdiffusion3 and plain-prediction helpers."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


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
    openfold = load("openfold_contract", OVERLAY / "openfold_predict_one.py")

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
        marker.write_text(json.dumps({"predictor": "alphafold3", "jobs": ["one"]}))
        expect(predict.completed_chunk(marker, ["one"], output),
               "completed prediction checkpoint was not reusable")
        expect(not predict.completed_chunk(marker, ["missing"], output),
               "a different job's structure satisfied the retry checkpoint")

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
