#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/audit_design_cardinality.py"
spec = importlib.util.spec_from_file_location("audit_design_cardinality", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


with tempfile.TemporaryDirectory(prefix="iproteinstudio-cardinality-") as raw:
    campaign = Path(raw)
    for run in range(1, 38):
        for cycle in range(8):
            pred_min = campaign / f"run_{run:03d}" / f"cycle_{cycle:02d}" / "pred_min"
            pred_min.mkdir(parents=True)
            (pred_min / "model_0.cif").write_text("data_test\n", encoding="utf-8")

    result = module.audit(campaign, trajectories=37, cycles=7)
    assert result["status"] == "complete", result
    assert result["actual_starting_structures"] == 37, result
    assert result["actual_optimized_designs"] == 259, result
    assert result["actual_total_checkpoints"] == 296, result
    assert result["cycle_00_counts_as_design"] is False, result

    (campaign / "run_037/cycle_07/pred_min/model_0.cif").unlink()
    failed = module.audit(campaign, trajectories=37, cycles=7)
    assert failed["status"] == "failed", failed
    assert failed["actual_optimized_designs"] == 258, failed
    assert failed["missing"] == ["run_037/cycle_07"], failed

print("PASS design cardinality contract (37 trajectories x 7 cycles)")
