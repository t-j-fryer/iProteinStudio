#!/usr/bin/env python3
"""Compare shipped engine locks without resolving or installing anything."""

from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
LOCK_ROOT = ROOT / "Sources/iProteinStudio/Resources/pipeline/locks"
OUTPUT = ROOT / "Validation/output/runtime_consolidation_v1/dependency_audit"
LOCKS = {
    "antifold": LOCK_ROOT / "antifold.txt",
    "boltz": LOCK_ROOT / "boltz.txt",
    "intellifold": LOCK_ROOT / "intellifold.txt",
    "lasermpnn": LOCK_ROOT / "lasermpnn.txt",
    "mpnn": LOCK_ROOT / "mpnn.txt",
    "openfold3": LOCK_ROOT / "openfold3.txt",
    "protenix": LOCK_ROOT / "protenix.txt",
    "protenix_constraint": LOCK_ROOT / "protenix_constraint.txt",
}
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        match = PIN.match(raw.strip())
        if match:
            packages[canonical(match.group(1))] = match.group(2)
    if not packages:
        raise RuntimeError(f"no pins parsed from {path}")
    return packages


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"refusing to overwrite existing audit: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    locks = {name: parse_lock(path) for name, path in LOCKS.items()}
    pairs: list[dict[str, object]] = []
    names = sorted(locks)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1:]:
            common = sorted(set(locks[left]) & set(locks[right]))
            conflicts = {
                package: [locks[left][package], locks[right][package]]
                for package in common
                if locks[left][package] != locks[right][package]
            }
            pairs.append({
                "left": left,
                "right": right,
                "shared_packages": len(common),
                "exact_shared_pins": len(common) - len(conflicts),
                "conflicting_pins": conflicts,
            })
    report = {
        "schema_version": 1,
        "locks": {
            name: {
                "path": str(LOCKS[name].relative_to(ROOT)),
                "package_count": len(packages),
                "python_stack_markers": {
                    package: packages.get(package)
                    for package in ("torch", "numpy", "pytorch-lightning", "esm", "fair-esm")
                    if package in packages
                },
            }
            for name, packages in locks.items()
        },
        "pairs": pairs,
    }
    (OUTPUT / "audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    lines = [
        "# Shipped runtime dependency comparison",
        "",
        "This is a static lock comparison, not evidence that environments are mergeable.",
        "",
        "| Engine | Packages | Torch | NumPy |",
        "|---|---:|---:|---:|",
    ]
    for name in names:
        packages = locks[name]
        lines.append(
            f"| {name} | {len(packages)} | {packages.get('torch', '—')} | "
            f"{packages.get('numpy', '—')} |"
        )
    lines.extend([
        "",
        "## Pairwise conflicts",
        "",
        "| Pair | Shared packages | Conflicting exact pins |",
        "|---|---:|---:|",
    ])
    for pair in sorted(pairs, key=lambda row: len(row["conflicting_pins"])):
        lines.append(
            f"| {pair['left']} + {pair['right']} | {pair['shared_packages']} | "
            f"{len(pair['conflicting_pins'])} |"
        )
    (OUTPUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(OUTPUT / "SUMMARY.md")


if __name__ == "__main__":
    main()
