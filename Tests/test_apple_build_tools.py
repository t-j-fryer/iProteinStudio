"""Exercise compiler setup, its real C++ probe, and early installer failure."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "Sources/iProteinStudio/Resources/pipeline"
HELPER = PIPELINE / "scripts/apple_build_tools.sh"


class AppleBuildToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="studio-compiler-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + ":" + os.environ["PATH"],
                        TMPDIR=str(self.root), IPROTEINSTUDIO_SETUP_CAFFEINATED="1",
                        IPROTEINSTUDIO_BUILD_FROM_SOURCE="1",
                        NANOHUNTER_ROOT=str(self.root / "support"))

    def script(self, name, contents):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -eu\n" + contents)
        path.chmod(0o755)
        return path

    def configure(self):
        return subprocess.run(["/bin/bash", "-uc", f"source {shlex.quote(str(HELPER))}; configure_apple_build_tools"],
                              env=self.env, text=True, capture_output=True)

    def test_real_compile_link_and_execution(self):
        # Also verifies a stale inherited SDK is replaced by xcrun's selection.
        self.env["SDKROOT"] = "/missing/old/sdk"
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("compile/link/run check passed", result.stdout)
        self.assertFalse(list(self.root.glob("iproteinstudio-compiler.*")))

    def test_build_subprocess_receives_sdk_headers(self):
        sdk = subprocess.check_output(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
        real_cxx = subprocess.check_output(["/usr/bin/xcrun", "--sdk", "macosx", "--find", "clang++"], text=True).strip()
        cxx = self.script("checked-clang++", '''
[[ "$SDKROOT" == "$EXPECTED_SDK" ]]
[[ "$CPLUS_INCLUDE_PATH" == "$EXPECTED_SDK/usr/include/c++/v1:/kept/custom/include" ]]
exec "$REAL_CXX" "$@"
''')
        self.script("xcrun", '''
if [[ "$*" == *"--find clang++" ]]; then
    echo "$CHECKED_CXX"
else
    exec /usr/bin/xcrun "$@"
fi
''')
        self.env.update(EXPECTED_SDK=sdk, REAL_CXX=real_cxx, CHECKED_CXX=str(cxx),
                        CPLUS_INCLUDE_PATH="/kept/custom/include")
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_compiler_failure_is_not_reported_as_success_and_cleans_probe(self):
        cxx = self.script("broken-clang++", "echo \"fatal error: 'cmath' file not found\" >&2\nexit 1\n")
        self.script("xcrun", '''
if [[ "$*" == *"--find clang++" ]]; then echo "$BROKEN_CXX"; else exec /usr/bin/xcrun "$@"; fi
''')
        self.env["BROKEN_CXX"] = str(cxx)
        result = self.configure()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cmath", result.stderr)
        self.assertFalse(list(self.root.glob("iproteinstudio-compiler.*")))

    def test_setup_stops_before_downloads_but_detection_still_works(self):
        self.script("xcrun", 'echo "test: no developer tools" >&2\nexit 1\n')
        result = subprocess.run(["bash", str(PIPELINE / "setup_pipeline.sh"), "--with-nesso"],
                                env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NHFAIL|Apple's C++ build tools", result.stdout)
        self.assertIn("NHREQUIRES|apple-build-tools", result.stdout)
        self.assertIn("Software Update", result.stdout)
        self.assertIn("Install Apple Tools", result.stdout)
        failure = next(line for line in result.stdout.splitlines() if line.startswith("NHFAIL|"))
        self.assertNotIn("Terminal", failure)
        self.assertNotIn("NHSTEP|python|", result.stdout)
        self.assertFalse((self.root / "support/toolchains").exists())
        self.assertFalse((self.root / "support/.install.lock").exists())
        detected = subprocess.run(["bash", str(PIPELINE / "setup_pipeline.sh"), "--detect"],
                                  env=self.env, text=True, capture_output=True)
        self.assertEqual(detected.returncode, 0, detected.stdout + detected.stderr)
        self.assertNotIn("test: no developer tools", detected.stderr)

    def test_missing_tools_do_not_open_apple_installer_implicitly(self):
        self.script("xcode-select", '''
[[ "$*" == "--print-path" ]] || { echo unexpected-installer-request >&2; exit 99; }
exit 2
''')
        self.script("xcrun", 'touch "$TMPDIR/unexpected-xcrun"\nexit 99\n')
        result = self.configure()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("have not been selected or installed", result.stderr)
        self.assertNotIn("unexpected-installer-request", result.stderr)
        self.assertFalse((self.root / "unexpected-xcrun").exists())

    def test_retry_rechecks_tools_and_runs_real_compiler(self):
        select = self.script("xcode-select", 'exit 2\n')
        self.assertNotEqual(self.configure().returncode, 0)
        select.unlink()
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("compile/link/run check passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
