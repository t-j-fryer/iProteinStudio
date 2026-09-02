#!/usr/bin/env python3
"""Behavioral tests for lossless output compaction and reference storage."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/storage_policy.py"
SPEC = importlib.util.spec_from_file_location("storage_policy_contract", SCRIPT)
assert SPEC and SPEC.loader
storage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storage)


def expect(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="iproteinstudio-storage-") as raw:
        root = Path(raw)
        original = root / "job_full_data_sample_0.json"
        payload = {"token_pair_pae": [[float(i + j) for j in range(160)]
                                      for i in range(160)],
                   "token_asym_id": [0] * 80 + [1] * 80}
        original.write_text(json.dumps(payload, separators=(",", ":")))
        source_bytes = original.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()

        receipt = storage.compact_detailed_confidence(root)
        compressed = Path(str(original) + ".gz")
        expect(not original.exists() and compressed.is_file(),
               "verified confidence JSON was not compacted")
        expect(gzip.open(compressed, "rb").read() == source_bytes,
               "compressed confidence does not reproduce the exact source bytes")
        expect(receipt["files"][0]["sha256"] == source_hash
               and receipt["compressed_bytes"] < receipt["original_bytes"],
               "compaction receipt lost checksum or byte provenance")
        expect(storage.read_json(compressed) == payload,
               "transparent compressed JSON reader changed the document")
        expect(storage.json_variants(root, "*_full_data_sample_*.json") == [compressed],
               "resume discovery did not find compressed Protenix confidence")

        # Simulate a crash after verified gzip publication but before original
        # deletion. The next pass may remove only the byte-proven duplicate.
        original.write_bytes(source_bytes)
        second = storage.compact_json(original)
        expect(not original.exists() and second["status"] == "verified_existing",
               "safe retry did not resolve a verified two-copy crash state")

        canonical = root / "engine" / "sample_0.cif"
        canonical.parent.mkdir()
        canonical.write_text("data_exact\n")
        alias = root / "pred_min" / "model_0.cif"
        expect(storage.relative_symlink(canonical, alias) == "linked"
               and alias.is_symlink() and alias.read_bytes() == canonical.read_bytes(),
               "normalized structure is not a valid relative reference")
        replacement = root / "engine" / "sample_1.cif"
        replacement.write_text("data_replacement\n")
        expect(storage.relative_symlink(replacement, alias, replace=True) == "linked"
               and alias.resolve() == replacement.resolve(),
               "successful rerun left a stale normalized result reference")

        msa = root / "outside" / "target.a3m"
        msa.parent.mkdir()
        msa.write_text(">query\nACDEFG\n>hit\nACDEFG\n")
        run_msa = root / "run" / "inputs" / "target.a3m"
        object_result = storage.materialize_object(msa, root / "objects", run_msa)
        msa.unlink()
        expect(run_msa.read_text().startswith(">query\nACDEFG")
               and Path(object_result["object"]).is_file(),
               "content-addressed MSA stopped being durable after source deletion")

        campaign = root / "campaign"
        cycle = campaign / "run_001" / "cycle_01" / "pred_min"
        cycle.mkdir(parents=True)
        result_structure = cycle / "model_0.cif"
        result_structure.write_text("data_result\n")
        gallery = campaign / "cifs_all" / "run_001_cycle_01_model_0.cif"
        storage.relative_symlink(result_structure, gallery)
        index = storage.campaign_index(campaign)
        expect(index["results"][0]["counts_as_design"] is True
               and index["results"][0]["aliases"] == [
                   "cifs_all/run_001_cycle_01_model_0.cif"
               ], "campaign reference index lost design or gallery provenance")

    print("PASS storage policy")


if __name__ == "__main__":
    main()
