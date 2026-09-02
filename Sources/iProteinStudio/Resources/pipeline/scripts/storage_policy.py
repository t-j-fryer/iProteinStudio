#!/usr/bin/env python3
"""Lossless, resumable storage policy for Studio prediction outputs.

Scientific outputs are never discarded merely because they are large.  Dense
confidence JSON is compressed only after a streamed SHA-256 round trip proves
that decompression reproduces the original bytes.  Canonical structures stay in
their engine output tree; compatibility/gallery paths are relative symlinks.
Immutable inputs are materialised through a content-addressed object store and
cloned, hard-linked, or copied into each run in that order of preference.
"""

from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
BLOCK = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(BLOCK), b""):
            value.update(block)
    return value.hexdigest()


def read_json(path: Path):
    """Read a plain or gzip-compressed JSON document."""
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def json_variants(root: Path, pattern: str) -> list[Path]:
    """Return one artifact per logical JSON name, preferring compressed form."""
    selected: dict[str, Path] = {}
    patterns = [pattern]
    if pattern.endswith(".json"):
        patterns.append(pattern + ".gz")
    for path in (item for candidate in patterns for item in root.rglob(candidate)):
        logical = str(path)[:-3] if path.name.endswith(".json.gz") else str(path)
        previous = selected.get(logical)
        if previous is None or path.stat().st_mtime_ns > previous.stat().st_mtime_ns:
            selected[logical] = path
    return [selected[key] for key in sorted(selected)]


def _stream_decompressed_digest(path: Path) -> tuple[str, int]:
    value = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(BLOCK), b""):
            value.update(block)
            size += len(block)
    return value.hexdigest(), size


def compact_json(path: Path) -> dict[str, object]:
    """Transactionally replace one JSON with a verified ``.json.gz`` artifact."""
    path = path.resolve()
    if path.name.endswith(".json.gz"):
        digest, size = _stream_decompressed_digest(path)
        return {"path": str(path), "sha256": digest, "original_bytes": size,
                "compressed_bytes": path.stat().st_size, "status": "already_compact"}
    if not path.is_file() or not path.name.endswith(".json"):
        raise ValueError(f"not a JSON file: {path}")

    target = Path(str(path) + ".gz")
    original_digest = sha256(path)
    original_size = path.stat().st_size
    if target.is_file():
        compressed_digest, compressed_size = _stream_decompressed_digest(target)
        if (compressed_digest, compressed_size) != (original_digest, original_size):
            raise ValueError(f"existing compressed artifact does not match {path}")
        path.unlink()
        return {"path": str(target), "sha256": original_digest,
                "original_bytes": original_size, "compressed_bytes": target.stat().st_size,
                "status": "verified_existing"}

    temporary = target.with_name(f".{target.name}.{os.getpid()}.part")
    temporary.unlink(missing_ok=True)
    try:
        with path.open("rb") as source, temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6,
                               mtime=0) as compressed:
                shutil.copyfileobj(source, compressed, length=BLOCK)
            raw.flush()
            os.fsync(raw.fileno())
        compressed_digest, compressed_size = _stream_decompressed_digest(temporary)
        if (compressed_digest, compressed_size) != (original_digest, original_size):
            raise ValueError(f"gzip verification failed for {path}")
        os.replace(temporary, target)
        # A crash before this unlink leaves two verified copies; the next pass
        # recognizes that state and removes only the proven duplicate.
        path.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(target), "sha256": original_digest,
            "original_bytes": original_size, "compressed_bytes": target.stat().st_size,
            "status": "compacted"}


def detailed_confidence_files(root: Path) -> list[Path]:
    files = list(root.rglob("*_full_data_sample_*.json"))
    files += [path for path in root.rglob("*_confidences.json")
              if "summary_confidences" not in path.name]
    return sorted(set(files))


def compact_detailed_confidence(root: Path) -> dict[str, object]:
    """Compact only losslessly recoverable dense confidence documents."""
    root = root.resolve()
    records = []
    failures = []
    for path in detailed_confidence_files(root):
        try:
            records.append(compact_json(path))
        except (OSError, ValueError) as error:
            # The original remains in place on every failure path.  Prediction
            # success is therefore not converted into failure by an optional
            # storage optimisation.
            failures.append({"path": str(path), "error": str(error)})
    receipt = {
        "schema_version": 1,
        "policy": "lossless-detailed-confidence-gzip",
        "created_epoch": time.time(),
        "files": records,
        "failures": failures,
        "original_bytes": sum(int(item["original_bytes"]) for item in records),
        "compressed_bytes": sum(int(item["compressed_bytes"]) for item in records),
    }
    if records or failures:
        destination = root / "storage_compaction.json"
        temporary = destination.with_suffix(".json.part")
        temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, destination)
    return receipt


def relative_symlink(source: Path, destination: Path, replace: bool = False) -> str:
    """Create an atomic relative reference without replacing unknown content."""
    source = source.resolve(strict=True)
    destination = destination.parent.resolve() / destination.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        try:
            if destination.resolve(strict=True) == source:
                return "existing_reference"
        except OSError:
            pass
        if not replace:
            # Inspection/migration callers do not replace unknown content.
            return "retained_existing"
    relative = os.path.relpath(source, destination.parent)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.link")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(relative)
    os.replace(temporary, destination)
    if destination.resolve(strict=True) != source:
        destination.unlink(missing_ok=True)
        raise OSError(f"reference verification failed: {destination}")
    return "linked"


def _clone_file(source: Path, destination: Path) -> bool:
    if os.uname().sysname != "Darwin":
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    clonefile = getattr(libc, "clonefile", None)
    if clonefile is None:
        return False
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    result = clonefile(os.fsencode(source), os.fsencode(destination), 0)
    return result == 0


def materialize_object(source: Path, object_root: Path, destination: Path) -> dict[str, str]:
    """Store immutable bytes by SHA-256 and materialise a durable run input."""
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"object source is not a file: {source}")
    digest = sha256(source)
    suffix = "".join(source.suffixes) or ".bin"
    object_path = object_root.resolve() / "sha256" / digest[:2] / f"{digest}{suffix}"
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists():
        if sha256(object_path) != digest:
            raise ValueError(f"content-addressed object is corrupt: {object_path}")
    else:
        fd, raw = tempfile.mkstemp(prefix=f".{digest}.", dir=object_path.parent)
        os.close(fd)
        temporary = Path(raw)
        try:
            shutil.copyfile(source, temporary)
            if sha256(temporary) != digest:
                raise ValueError(f"object staging verification failed for {source}")
            os.chmod(temporary, 0o444)
            try:
                os.link(temporary, object_path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        if not object_path.is_file() or sha256(object_path) != digest:
            raise ValueError(f"object publication failed for {source}")

    destination = destination.parent.resolve() / destination.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if destination.is_file() and sha256(destination) == digest:
            return {"sha256": digest, "object": str(object_path),
                    "destination": str(destination), "method": "existing"}
        raise ValueError(f"refusing to replace changed run input: {destination}")
    method = "clone"
    if not _clone_file(object_path, destination):
        try:
            os.link(object_path, destination)
            method = "hardlink"
        except OSError:
            shutil.copy2(object_path, destination)
            method = "copy"
    if sha256(destination) != digest:
        destination.unlink(missing_ok=True)
        raise ValueError(f"materialised object verification failed: {destination}")
    return {"sha256": digest, "object": str(object_path),
            "destination": str(destination), "method": method}


def campaign_index(root: Path) -> dict[str, object]:
    root = root.resolve()
    records = []
    for structure in sorted(root.glob("run_*/cycle_*/pred_min/model_0.*")):
        if structure.suffix.lower() not in {".cif", ".pdb"}:
            continue
        cycle = structure.parents[1].name
        run = structure.parents[2].name
        canonical = structure.resolve(strict=True)
        aliases = []
        expected = f"{run}_{cycle}_model_0.cif"
        for gallery in root.glob("cifs_*"):
            candidate = gallery / expected
            if candidate.exists() or candidate.is_symlink():
                aliases.append(candidate.relative_to(root).as_posix())
        records.append({
            "run": run,
            "cycle": cycle,
            "counts_as_design": cycle != "cycle_00",
            "structure": structure.relative_to(root).as_posix(),
            "canonical_structure": canonical.relative_to(root).as_posix()
                if canonical.is_relative_to(root) else str(canonical),
            "aliases": aliases,
        })
    payload = {"schema_version": 1, "policy": "canonical-structures-with-references",
               "results": records}
    target = root / "results_index.json"
    temporary = target.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, target)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compact = subparsers.add_parser("compact-confidence")
    compact.add_argument("--root", type=Path, required=True)
    link = subparsers.add_parser("link")
    link.add_argument("--source", type=Path, required=True)
    link.add_argument("--destination", type=Path, required=True)
    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--source", type=Path, required=True)
    materialize.add_argument("--object-root", type=Path, required=True)
    materialize.add_argument("--destination", type=Path, required=True)
    index = subparsers.add_parser("index-campaign")
    index.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "compact-confidence":
        result = compact_detailed_confidence(args.root)
    elif args.command == "link":
        result = {"status": relative_symlink(args.source, args.destination, replace=True)}
    elif args.command == "materialize":
        result = materialize_object(args.source, args.object_root, args.destination)
    else:
        result = campaign_index(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
