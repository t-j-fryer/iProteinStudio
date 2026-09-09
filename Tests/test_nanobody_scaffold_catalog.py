"""Exercise scaffold provenance and the actual CDR resolver without inference."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

PIPELINE = Path(__file__).resolve().parents[1] / "Sources/iProteinStudio/Resources/pipeline"
CATALOG = PIPELINE / "examples/nanobody_scaffolds/catalog.tsv"


class ScaffoldCatalog(unittest.TestCase):
    def test_catalog_integrity(self):
        with CATALOG.open(newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(len(rows), 8)
        self.assertEqual(len({row["scaffold_id"] for row in rows}), len(rows))
        for row in rows:
            sequence = row["sequence"]
            self.assertTrue(set(sequence) <= set("ACDEFGHIKLMNPQRSTVWY"))
            previous_end = 0
            for cdr in (1, 2, 3):
                start, end = map(int, row[f"cdr{cdr}_range_1based"].split("-"))
                self.assertTrue(previous_end < start <= end <= len(sequence))
                previous_end = end
            self.assertEqual(end - start + 1, int(row["cdr3_length"]))

    def test_3eak_exact_domain_and_recorded_cdr_provenance(self):
        with CATALOG.open(newline="") as handle:
            row = next(r for r in csv.DictReader(handle, delimiter="\t")
                       if r["scaffold_id"] == "3eak_nbbcii10_fgla")
        sources = CATALOG.parent / "sources"
        deposited = (sources / "3eak_deposited.fasta").read_bytes()
        provenance = json.loads((sources / "3eak_provenance.json").read_text())
        self.assertEqual(hashlib.sha256(deposited).hexdigest(), provenance["source_sha256"])
        original = "".join(line for line in deposited.decode().splitlines() if not line.startswith(">"))
        self.assertEqual(original, row["sequence"] + "RGRHHHHHH")
        self.assertEqual(len(row["sequence"]), 128)
        self.assertEqual(hashlib.sha256(row["sequence"].encode()).hexdigest(), provenance["sequence_sha256"])
        self.assertFalse(provenance["independent_numbering_validated"])
        result = subprocess.run([
            sys.executable, str(PIPELINE / "scripts/nanobody_cdrs.py"),
            "--seq", row["sequence"], "--catalog", str(CATALOG), "--emit", "json",
        ], check=True, capture_output=True, text=True)
        resolved = json.loads(result.stdout)
        self.assertEqual(resolved["method"], "catalog")
        self.assertIn("not independently numbered", resolved["detail"])
        self.assertEqual(resolved["ranges"], provenance["cdr_resolution_before_catalog_insertion"]["ranges"])


if __name__ == "__main__":
    unittest.main()
