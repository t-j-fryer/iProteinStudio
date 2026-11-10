"""Execute real asset staging and failure recovery without an app or model inference."""
from __future__ import annotations
import fcntl
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
RESOURCES = REPO / "Sources/iProteinStudio/Resources"
SCRIPT = RESOURCES / "pipeline/scripts/stage_assets.py"
spec = importlib.util.spec_from_file_location("stage_assets", SCRIPT)
stage_assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_assets)


class HeadlessInstallTests(unittest.TestCase):
    def test_older_payload_cannot_replace_newer_installed_release(self):
        self.assertEqual(self.run_stage().returncode, 0)
        manifest = self.root / 'WORKFLOW_RELEASE.json'
        value = json.loads(manifest.read_text())
        value['generation'] += 1
        manifest.write_text(json.dumps(value))
        before = (self.root / 'scripts/esmfold2_predict.py').read_bytes()
        result = self.run_stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('older workflows', result.stderr)
        self.assertEqual(json.loads(manifest.read_text()), value)
        self.assertEqual((self.root / 'scripts/esmfold2_predict.py').read_bytes(), before)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-headless-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "managed"
        self.root.mkdir()

    def run_stage(self, root=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--resources", str(RESOURCES),
                               "--root", str(root or self.root)], capture_output=True, text=True)

    def test_real_payload_and_update_preserve_user_data_and_cached_msas(self):
        project = self.root / "projects/demo/private.txt"
        project.parent.mkdir(parents=True)
        project.write_text("synthetic user data")
        weights = self.root / "models/keep.pt"
        weights.parent.mkdir()
        weights.write_text("synthetic, not weights")
        cached = self.root / "scaffold_msa_cache/7eow_caplacizumab/full_msa.a3m"
        cached.parent.mkdir(parents=True)
        cached.write_text("user supplied alignment")
        first = self.run_stage()
        self.assertEqual(first.returncode, 0, first.stderr)
        receipt = json.loads((self.root / "receipts/headless-assets.json").read_text())
        for name in ["mcp/server.py", "rfd3_scripts/predict_batch.py", "rfd3_overlay/OVERLAY_VERSION",
                     "examples_data/t4_lysozyme/target.pdb", "bin/studioctl", "bin/studio-mcp"]:
            self.assertTrue(name in receipt["files"], name)
            self.assertTrue((self.root / name).is_file(), name)
        self.assertFalse(list((self.root / "scripts").rglob("*.pyc")))
        (self.root / "scripts/test-unshipped.py").write_text("stale helper")
        second = self.run_stage()
        self.assertEqual(second.returncode, 0, second.stderr)
        updated = json.loads((self.root / "receipts/headless-assets.json").read_text())
        self.assertEqual(receipt["assets_sha256"], updated["assets_sha256"])
        self.assertFalse((self.root / "scripts/test-unshipped.py").exists())
        self.assertEqual(project.read_text(), "synthetic user data")
        self.assertEqual(weights.read_text(), "synthetic, not weights")
        self.assertEqual(cached.read_text(), "user supplied alignment")
        self.assertFalse(list(self.root.glob(".headless-stage-*")))

    def test_active_execution_lease_blocks_before_any_assets_change(self):
        agent = self.root / "agent"
        agent.mkdir()
        with (agent / "execution.lock").open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active work", result.stderr)
        self.assertFalse((self.root / "scripts").exists())

    def test_live_installer_and_unknown_lock_ownership_are_not_overwritten(self):
        lock = self.root / ".install.lock"
        lock.mkdir()
        (lock / "pid").write_text(str(os.getpid()))
        result = self.run_stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another Studio installation", result.stderr)
        (lock / "pid").unlink()
        result = self.run_stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(lock.is_dir())

    def test_failed_update_rolls_back_every_activated_asset(self):
        self.assertEqual(self.run_stage().returncode, 0)
        (self.root / "PIPELINE_VERSION").write_text("previous install")
        original = stage_assets.os.replace
        def fail_on_scripts(source, target):
            if Path(target) == self.root / "scripts" and Path(source).parent.name == "payload":
                raise OSError("synthetic disk failure")
            return original(source, target)
        with patch.object(stage_assets.os, "replace", side_effect=fail_on_scripts):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                stage_assets.stage(RESOURCES, self.root)
        self.assertEqual((self.root / "PIPELINE_VERSION").read_text(), "previous install")
        self.assertTrue((self.root / "scripts/download_verified.py").is_file())
        self.assertFalse(list(self.root.glob(".headless-stage-*")))

    def test_hard_interruption_is_recovered_on_next_invocation(self):
        self.assertEqual(self.run_stage().returncode, 0)
        (self.root / "PIPELINE_VERSION").write_text("preserve after interruption")
        child = '''import importlib.util,os,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('stage',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
old=m.os.replace
def interrupt(a,b):
    old(a,b)
    if Path(b).name=='scripts' and Path(a).parent.name=='payload':os._exit(91)
m.os.replace=interrupt
m.stage(Path(sys.argv[2]),Path(sys.argv[3]))
'''
        result = subprocess.run([sys.executable, "-c", child, str(SCRIPT), str(RESOURCES), str(self.root)])
        self.assertEqual(result.returncode, 91)
        self.assertTrue(list(self.root.glob(".headless-stage-*")))
        stage_assets.recover(self.root)
        self.assertEqual((self.root / "PIPELINE_VERSION").read_text(), "preserve after interruption")
        self.assertEqual(self.run_stage().returncode, 0)

    def test_symlink_cannot_redirect_staging_outside_managed_root(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "agent").symlink_to(outside)
        result = self.run_stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((outside / "execution.lock").exists())

    def test_help_and_detection_need_no_python_git_or_desktop(self):
        env = dict(os.environ, PATH="/usr/bin:/bin", NANOHUNTER_ROOT=str(self.root))
        for args in [["--help"], ["--detect"], ["--setup-help"]]:
            result = subprocess.run(["/bin/bash", str(REPO / "install.sh"), *args], env=env,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("xcode-select", result.stderr)
        self.assertFalse((self.root / "components").exists())

    def test_invalid_options_do_not_bootstrap_or_stage(self):
        for args in [["--with-typo"], ["--stage-only", "--base"], ["--detect", "--base"], ["--root"]]:
            result = subprocess.run(["/bin/bash", str(REPO / "install.sh"), "--root", str(self.root), *args],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "toolchains").exists())

    def test_cli_project_creation_needs_no_gui_and_rejects_unsafe_paths(self):
        env = dict(os.environ, NANOHUNTER_ROOT=str(self.root))
        command = [sys.executable, str(RESOURCES / "pipeline/mcp/studioctl.py")]
        first = subprocess.run([*command, "project-create", "demo"], env=env, text=True, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        repeated = subprocess.run([*command, "project-create", "demo"], env=env, text=True, capture_output=True)
        self.assertEqual(json.loads(first.stdout), json.loads(repeated.stdout))
        listing = subprocess.run([*command, "projects"], env=env, text=True, capture_output=True)
        self.assertIn('"demo"', listing.stdout)
        outside = self.base / "external-project"
        outside.mkdir()
        (self.root / "projects/escape").symlink_to(outside)
        for name in ["../escape", "escape", "bad/name"]:
            result = subprocess.run([*command, "project-create", name], env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0, name)

    @unittest.skipUnless(platform.system() == "Darwin" and platform.machine() == "arm64", "native Mac entry point")
    def test_source_archive_and_bundle_entrypoints_forward_selections_and_failures(self):
        # A real resource payload and real doctor/server, with only the network
        # component installer replaced. No production test bypass is exposed.
        archive = self.base / "extracted source"
        resources = archive / "Sources/iProteinStudio/Resources"
        shutil.copytree(RESOURCES, resources, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copy2(REPO / "install.sh", archive / "install.sh")
        control = self.root / "components/control/current/python/bin"
        control.mkdir(parents=True)
        (control / "python3").symlink_to(sys.executable)
        fake = resources / "pipeline/setup_pipeline.sh"
        fake.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$NANOHUNTER_ROOT/selected-args"\nexit "${FIXTURE_SETUP_EXIT:-0}"\n')
        result = subprocess.run(["/bin/bash", str(archive / "install.sh"), "--root", str(self.root),
                                 "--with-boltz", "--with-rfd4", "--with-esmfold2-600"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root/'selected-args').read_text().splitlines(),
                         ['--with-boltz','--with-rfd4','--with-esmfold2-600'])
        bundle = self.base / "extracted app/iProteinStudio.app/Contents/Resources/iProteinStudioResources"
        shutil.copytree(resources, bundle)
        before = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in bundle.rglob('*') if p.is_file()}
        result = subprocess.run(["/bin/bash", str(bundle/'pipeline/install_cli.sh'), "--root", str(self.root),
                                 "--stage-only"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in bundle.rglob('*') if p.is_file()}
        self.assertEqual(after, before, 'Headless installation modified its signed resource bundle')
        self.assertEqual((self.root/'selected-args').read_text().splitlines(), ['--retry-components','control'])
        info = bundle.parent.parent/'Info.plist'
        info.write_bytes(plistlib.dumps({'IPStudioLocalBeta':'1'}))
        result = subprocess.run(["/bin/bash", str(bundle/'pipeline/install_cli.sh'), "--root", str(self.root),
                                 "--stage-only"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Local Beta bundles cannot',result.stderr)
        result = subprocess.run(["/bin/bash", str(archive/'install.sh'), "--root", str(self.root), "--base"],
                                env={**os.environ,'FIXTURE_SETUP_EXIT':'7'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertNotIn('Studio CLI:',result.stdout)


if __name__ == "__main__":
    unittest.main()
