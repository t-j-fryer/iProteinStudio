import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("vendor", Path(__file__).resolve().parents[1] / "tools/vendor_pipeline.py")
vendor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vendor)


class VendorTests(unittest.TestCase):
    def test_staging_keeps_local_policy_and_apply_refuses_manual_merge(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            repo, upstream = root / "studio", root / "upstream"
            local = repo / "Sources/iProteinStudio/Resources/pipeline"
            local.mkdir(parents=True); upstream.mkdir(); (repo / "tools").mkdir()
            (local / "nanohunter_run.sh").write_text("Studio policy")
            (upstream / "nanohunter_run.sh").write_text("different upstream policy")
            (repo / "tools/pipeline-vendor-manifest.json").write_text(json.dumps({"files": {
                "nanohunter_run.sh": {"policy": "manual-merge", "studio_sha256": vendor.digest(local / "nanohunter_run.sh")}}}))
            with patch.object(vendor.subprocess, "check_output", side_effect=["revision\n", ""]):
                review = vendor.stage(upstream, repo)
            self.assertEqual((local / "nanohunter_run.sh").read_text(), "Studio policy")
            with self.assertRaisesRegex(ValueError, "manually merging"):
                vendor.apply(review, repo)
            self.assertEqual((local / "nanohunter_run.sh").read_text(), "Studio policy")
            (review / "files/nanohunter_run.sh").write_text("tampered review")
            with self.assertRaisesRegex(ValueError, "changed after review"):
                vendor.apply(review, repo)


if __name__ == "__main__":
    unittest.main()
