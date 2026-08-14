#!/usr/bin/env python3
"""Launch a long RFD3–NISE campaign detached under caffeinate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", default="all")
    args = parser.parse_args()
    config = args.config.resolve()
    cfg = json.loads(config.read_text())
    campaign = Path(cfg["campaign_dir"])
    if not campaign.is_absolute():
        campaign = (ROOT / campaign).resolve()
    campaign.mkdir(parents=True, exist_ok=True)
    pid_path = campaign / "campaign.pid"
    if pid_path.exists():
        try:
            os.kill(int(pid_path.read_text().strip()), 0)
            raise SystemExit(f"campaign process already alive: PID {pid_path.read_text().strip()}")
        except ProcessLookupError:
            pid_path.unlink()

    cmd = [
        "caffeinate", "-dimsu", sys.executable, str(ROOT / "scripts" / "run_rfd3_nise_campaign.py"),
        "--config", str(config), "--stage", args.stage,
    ]
    if os.fork() == 0:
        os.setsid()
        if os.fork() == 0:
            os.chdir(ROOT)
            mpl_cache = campaign / ".matplotlib"
            mpl_cache.mkdir(exist_ok=True)
            os.environ.update(
                DEBUG="false", TOKENIZERS_PARALLELISM="false",
                MPLCONFIGDIR=str(mpl_cache),
            )
            log = os.open(campaign / "campaign.stdout.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.dup2(log, 1)
            os.dup2(log, 2)
            os.close(0)
            pid_path.write_text(str(os.getpid()) + "\n")
            os.execvp(cmd[0], cmd)
        os._exit(0)
    print(f"launched {campaign}; inspect {campaign / 'campaign.stdout.log'}")


if __name__ == "__main__":
    main()
