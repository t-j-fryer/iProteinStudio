#!/usr/bin/env python3
"""Run the bundled partial and motif examples through Foundry's real preflight."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "Sources/iProteinStudio/Resources/rfd3/prepare_campaign.py"
STRUCTURE = ROOT / "Sources/iProteinStudio/Resources/examples/p53_mdm2/1YCR.pdb"
MDM2 = "ETLVRPKPLLLKLLKSVGAQKDTYTMKEVLFYLGQYIMTKRLYDEKQQHIVYCSNDLLGDLFGVPSFSVKEHRKIYTMIYRNLVV"


def request(mode: str, campaign: Path, rfd3_root: Path) -> dict:
    value = {
        "campaign_dir": str(campaign),
        "rfd3_root": str(rfd3_root),
        "nanohunter_root": str(ROOT),
        "design_name": "p53_mdm2_example",
        "design_mode": mode,
        "target_kind": "protein",
        "target_structure": str(STRUCTURE),
        "target_chain": "A",
        "target_chains": ["A"],
        "target_sequence": MDM2,
        "source_binder_chain": "B",
        "lengths": [70],
        "num_backbones": 1,
        "batch_size": 1,
        "queues_per_bin": 1,
        "timesteps": 20,
        "recycles": 1,
        "precision": "fp32",
        "seed_base": 1,
        "sequences_per_backbone": 1,
        "top_n": 1,
        "sequence_model": "solublempnn",
        "extra_predictors": ["boltz"],
        "run_apo": True,
        "hit_filters": {},
    }
    if mode == "partialDiffusion":
        value.update(partial_t=1.0, preserve_partial_sequence=True, motif_sites={})
    else:
        value["motif_sites"] = {
            "B19": "CG,CE1,CZ",
            "B23": "CG,NE1,CH2",
            "B26": "CG,CD1,CD2",
        }
    return value


def main() -> None:
    rfd3_root = Path(sys.argv[1] if len(sys.argv) > 1 else
                     Path.home() / ".iproteinstudio/rfd3").resolve()
    if not (rfd3_root / "scripts/design_from_yaml.py").exists():
        raise SystemExit(f"RFdiffusion3 installation unavailable: {rfd3_root}")
    with tempfile.TemporaryDirectory(prefix="iproteinstudio-rfd3-examples-") as raw:
        work = Path(raw)
        for mode in ("partialDiffusion", "motifScaffolding"):
            payload = work / f"{mode}.json"
            payload.write_text(json.dumps(request(mode, work / mode, rfd3_root), indent=2) + "\n")
            result = subprocess.run([sys.executable, str(PREPARE), str(payload)],
                                    text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "PREPOK|" in result.stdout
            config = json.loads((work / mode / "config/campaign.json").read_text())
            yaml = (work / mode / "config/design.yaml").read_text()
            assert config["source_binder_contig"] == "A17-29"
            assert config["target_chains"] == ["B"]
            if mode == "partialDiffusion":
                assert "partial_t: 1" in yaml and '"B25-109": "ALL"' in yaml
                assert "infer_ori_strategy" not in yaml
            else:
                assert config["motif_sites"] == {
                    "A19": "CG,CE1,CZ", "A23": "CG,NE1,CH2", "A26": "CG,CD1,CD2"
                }
                assert 'unindex: "A19,A23,A26"' in yaml

    print("Bundled RFdiffusion3 partial and motif examples: Foundry preflight PASS")


if __name__ == "__main__":
    main()
