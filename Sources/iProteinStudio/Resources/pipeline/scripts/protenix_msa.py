#!/usr/bin/env python3
"""Generate one reusable A3M with Protenix's upstream MSA server client.

Protenix writes taxonomically pairable and environmental hits separately.
iProteinStudio's cache is per chain, so this adapter combines both groups while
retaining the query exactly once. Upstream's query-only recovery output is
rejected: a requested MSA must never silently degrade to single-sequence mode.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def canonical(sequence: str) -> str:
    return "".join(char for char in sequence.upper() if char.isalpha())


def query_from_a3m(path: Path) -> str:
    try:
        records = [record for record in path.read_text(errors="replace").split(">")
                   if record.strip()]
    except OSError:
        return ""
    if not records:
        return ""
    lines = records[0].splitlines()
    body = "".join(lines[1:])
    return "".join(char for char in body
                   if not char.islower() and char not in "-.").upper()


def combine(sources: list[Path], destination: Path, sequence: str) -> int:
    query = canonical(sequence)
    hits: list[tuple[str, str]] = []
    seen_alignments: set[str] = set()
    for source in sources:
        try:
            records = [record for record in source.read_text(errors="replace").split(">")
                       if record.strip()]
        except OSError:
            continue
        for record in records:
            lines = record.splitlines()
            if len(lines) < 2:
                continue
            header = lines[0].strip() or "hit"
            aligned = "".join(lines[1:]).strip()
            bare = "".join(char for char in aligned
                           if not char.islower() and char not in "-.").upper()
            if not aligned or bare == query or aligned in seen_alignments:
                continue
            seen_alignments.add(aligned)
            hits.append((header, aligned))

    if not hits:
        raise RuntimeError(
            "Protenix returned no homologs (its query-only recovery output is not a real MSA)"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    lines = [">query", query]
    for header, aligned in hits:
        lines.extend([f">{header}", aligned])
    partial.write_text("\n".join(lines) + "\n")
    if query_from_a3m(partial) != query:
        partial.unlink(missing_ok=True)
        raise RuntimeError("generated A3M query does not match the requested sequence")
    os.replace(partial, destination)
    return len(hits)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nanohunter-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    sequence = canonical(args.sequence)
    if not sequence:
        raise SystemExit("Protenix MSA: sequence is empty")
    root = args.nanohunter_root.expanduser().resolve()
    executable = root / "venvs" / "NanoHunter_protenix" / "bin" / "protenix"
    source = root / "src" / "Protenix"
    if not executable.is_file() or not source.is_dir():
        raise SystemExit("Protenix MSA: Protenix is not installed")

    work = args.work_dir.expanduser().resolve()
    shutil.rmtree(work, ignore_errors=True)
    search = work / "search"
    work.mkdir(parents=True, exist_ok=True)
    fasta = work / "query.fasta"
    fasta.write_text(f">query\n{sequence}\n")
    environment = dict(os.environ)
    environment.update({
        "PROTENIX_ROOT_DIR": str(root / "models" / "protenix"),
        "MPLCONFIGDIR": str(root / "matplotlib_cache"),
    })
    completed = subprocess.run(
        [str(executable), "msa", "--input", str(fasta),
         "--out_dir", str(search), "--msa_server_mode", "protenix"],
        cwd=source, env=environment,
    )
    if completed.returncode:
        raise SystemExit(completed.returncode)
    sources = sorted(search.rglob("pairing.a3m"))
    sources += sorted(search.rglob("non_pairing.a3m"))
    try:
        count = combine(sources, args.output.expanduser().resolve(), sequence)
    except RuntimeError as error:
        raise SystemExit(f"Protenix MSA: {error}") from error
    shutil.rmtree(work, ignore_errors=True)
    print(f"Protenix MSA: wrote {count} homologs to {args.output}")


if __name__ == "__main__":
    main()
