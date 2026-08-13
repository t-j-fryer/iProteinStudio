#!/usr/bin/env python3
"""Report concise progress for a configured RFD3–NISE campaign."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(path: Path) -> int:
    return sum(1 for _ in csv.DictReader(path.open())) if path.exists() else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--tail", type=int, default=12)
    args = parser.parse_args()
    cfg = json.loads(args.config.resolve().read_text())
    campaign = Path(cfg["campaign_dir"])
    if not campaign.is_absolute():
        campaign = (ROOT / campaign).resolve()

    alive = False
    pid = None
    pid_path = campaign / "campaign.pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            alive = True
        except (ValueError, ProcessLookupError):
            pass
    progress_path = campaign / "campaign_progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    counts = {
        "backbones": len(list((campaign / "rfd3" / "backbones").glob("design_*.pdb"))),
        "sequences": csv_rows(campaign / "mpnn" / "sequences.csv"),
        "holo_predictions": csv_rows(campaign / "predictions" / "holo" / "prediction_metrics.csv"),
        "scored": csv_rows(campaign / "analysis" / "scored_designs.csv"),
        "top": csv_rows(campaign / "analysis" / "top100.csv"),
        "apo_predictions": csv_rows(campaign / "predictions" / "apo" / "prediction_metrics.csv"),
        "rmsd_rows": csv_rows(campaign / "analysis" / "rmsd_metrics.csv"),
    }
    print(json.dumps({
        "campaign": str(campaign), "process_alive": alive, "pid": pid,
        "current_stage": progress.get("current_stage"),
        "completed_stages": progress.get("completed_stages", []), "counts": counts,
    }, indent=2))
    log = campaign / "campaign.stdout.log"
    if log.exists() and args.tail:
        print(f"\n--- tail {log} ---")
        print("\n".join(log.read_text(errors="replace").splitlines()[-args.tail:]))


if __name__ == "__main__":
    main()
