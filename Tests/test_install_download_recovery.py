#!/usr/bin/env python3
"""Execute fallback HTTP transfers and real installer component boundaries."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
DOWNLOADER = PIPELINE / 'scripts/download_verified.py'
SETUP = (PIPELINE / 'setup_pipeline.sh').read_text()
sha = lambda data: hashlib.sha256(data).hexdigest()


class Server(http.server.BaseHTTPRequestHandler):
    requests = []
    primary = b'original serialization'
    alternative = b'equivalent serialization'

    def do_GET(self):
        self.requests.append((self.path, self.headers.get('Range')))
        if self.path == '/unavailable':
            self.send_error(503)
            return
        data = self.primary if self.path == '/primary' else self.alternative
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Server.requests = []
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Server)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.output = self.root / 'checkpoint.pt'
        self.provenance = self.root / 'source.json'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_download(self, primary='/unavailable', corrupt=False):
        sources = [dict(name='original', url=self.base + primary, sha256=sha(Server.primary), retries=1, timeout=0.5),
                   dict(name='mirror', url=self.base + '/mirror', sha256=sha(b'wrong' if corrupt else Server.alternative), retries=1, timeout=0.5)]
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'sources': sources}))
        return subprocess.run([sys.executable, str(DOWNLOADER), '--sources', str(manifest),
                               '--output', str(self.output), '--provenance', str(self.provenance),
                               '--label', 'fixture'], capture_output=True, text=True, timeout=10)

    def test_unavailable_primary_uses_verified_alternative_and_records_source(self):
        self.output.with_suffix('.pt.part').write_bytes(b'old original bytes')
        result = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), Server.alternative)
        self.assertEqual(Server.requests, [('/unavailable', 'bytes=18-'), ('/mirror', None)])
        record = json.loads(self.provenance.read_text())
        self.assertEqual(record['sha256'], sha(Server.alternative))
        self.assertEqual(record['url'], self.base + '/mirror')
        self.assertFalse(record['cached'])

    def test_cached_either_variant_needs_no_network(self):
        for data, name in [(Server.primary, 'original'), (Server.alternative, 'mirror')]:
            self.output.write_bytes(data)
            result = self.run_download()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Server.requests, [])
            record = json.loads(self.provenance.read_text())
            self.assertEqual(record['source'], name)
            self.assertTrue(record['cached'])

    def test_primary_success_does_not_contact_mirror(self):
        result = self.run_download(primary='/primary')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Server.requests, [('/primary', None)])
        self.assertEqual(self.output.read_bytes(), Server.primary)

    def test_corrupt_primary_can_only_fall_back_to_pinned_alternative(self):
        result = self.run_download(primary='/mirror')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('checksum mismatch', result.stdout)
        self.assertEqual(self.output.read_bytes(), Server.alternative)

    def test_all_sources_fail_leaves_no_usable_artifact_or_stale_provenance(self):
        self.output.write_bytes(b'corrupted old checkpoint')
        self.provenance.write_text('{}')
        result = self.run_download(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.provenance.exists())
        self.assertIn('No approved source', result.stderr)

    def test_mirror_complete_partial_is_reused(self):
        partial = self.output.with_name(self.output.name + '.' + sha(Server.alternative) + '.part')
        partial.write_bytes(Server.alternative)
        result = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Server.requests, [('/unavailable', None)])
        self.assertEqual(self.output.read_bytes(), Server.alternative)


class ComponentRecoveryTests(unittest.TestCase):
    def run_shell(self, body, root):
        header = 'set -uo pipefail\n' + 'source ' + shlex.quote(str(PIPELINE / 'scripts/install_components.sh')) + '\n'
        header += 'state() { echo "NHSTATE|$1|$2|$3"; }; step() { :; }\n'
        return subprocess.run(['/bin/bash', '-c', header + body], cwd=root, text=True, capture_output=True, timeout=10)

    def test_shipped_source_manifest_matches_tensor_equivalence_audit(self):
        manifest = json.loads((PIPELINE/'scripts/abmpnn_sources.json').read_text())['sources']
        audit = json.loads((ROOT/'lab_book/artifacts/0123-abmpnn-mirror-verification.json').read_text())
        self.assertEqual(manifest[0]['sha256'], audit['original_sha256'])
        self.assertEqual(manifest[1]['sha256'], audit['mirror_sha256'])
        self.assertEqual(manifest[1]['url'], audit['url'])
        self.assertEqual(audit['differences'], [])

    def test_failure_continues_but_dependent_is_not_run_and_parent_lock_is_retained(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_shell('''
trap 'touch parent-exited' EXIT
touch install-lock
bad() { fail "HTTP 503"; }
good() { test -f install-lock || exit 99; touch later-engine; }
forbidden() { touch dependent-must-not-run; }
run_install_component base bad
[[ ! -e parent-exited ]] || exit 98
run_install_component child forbidden base
run_install_component independent good
finish_install_components
''', root)
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            self.assertTrue(Path(root, 'later-engine').exists())
            self.assertTrue(Path(root, 'parent-exited').exists())
            self.assertFalse(Path(root, 'dependent-must-not-run').exists())
            self.assertIn('NHDONE|partial|base child', result.stdout)

    def test_retry_runs_only_failed_components(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_shell('''
INSTALL_ONLY=abmpnn
already_done() { touch must-not-reinstall; }
retry() { touch retried; }
run_install_component mpnn already_done
run_install_component abmpnn retry mpnn
run_install_component boltz already_done
finish_install_components
''', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(Path(root, 'retried').exists())
            self.assertFalse(Path(root, 'must-not-reinstall').exists())
            self.assertIn('NHDONE|ok', result.stdout)

    def test_actual_core_commits_before_abmpnn_failure_and_later_component_runs(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path/'venv/bin').mkdir(parents=True)
            python = path/'venv/bin/python'
            python.write_text('#!/bin/bash\n[[ "$1" == "-c" ]] && exit 0\nexit 1\n')
            python.chmod(0o755)
            (path/'repo').mkdir()
            body = f'''
LIGAND_VENV={shlex.quote(str(path/'venv'))}
LIGANDMPNN_REPO={shlex.quote(str(path/'repo'))}
LIGANDMPNN_REV=fixture
PYTHON_BIN=unused
MPNN_LOCK=unused
VERIFIED_DOWNLOADER=unused
NESSO_SCRIPT_ROOT=unused
WITH_ABMPNN=1
begin_versioned_venv() {{ TRANSACTION_VENV="$LIGAND_VENV"; TRANSACTION_REUSED=1; }}
ensure_pinned_repo() {{ :; }}
download_verified_artifact() {{ touch "$2"; }}
commit_versioned_venv() {{ touch core-committed; }}
write_component_receipt() {{ echo "$*" >> receipts; }}
'''
            # Run the exact production functions and their orchestration, with
            # only external package/model operations replaced by fixtures.
            body += SETUP[SETUP.index('install_mpnn() {'):SETUP.index('# ---- AntiFold ----')]
            body += '\nlater() { touch later-engine; }; run_install_component later later\nfinish_install_components\n'
            result = self.run_shell(body, root)
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            self.assertTrue((path/'core-committed').exists())
            self.assertTrue((path/'later-engine').exists())
            self.assertIn('NHSTATE|mpnn|ok', result.stdout)
            self.assertIn('NHCOMPONENTFAIL|abmpnn|', result.stdout)
            self.assertNotIn('abmpnn.pt=', (path/'receipts').read_text())

    def test_optional_download_failure_preserves_each_completed_base_runtime(self):
        for base, extra in [('boltz', 'boltz_affinity'), ('intellifold', 'intellifold_full'), ('protenix', 'protenix_v2')]:
            with self.subTest(base=base), tempfile.TemporaryDirectory() as root:
                path = Path(root)
                venv = path/'venv'
                (venv/'bin').mkdir(parents=True)
                python = venv/'bin/python'
                python.write_text('#!/bin/bash\ncase "$*" in *protenix-v2.pt*) exit 1 ;; esac\nexit 0\n')
                python.chmod(0o755)
                (path/'models/mols').mkdir(parents=True)
                patch = path/'patch'; patch.touch()
                body = f'''
NANOHUNTER_ROOT={shlex.quote(root)}
BOLTZ_VENV={shlex.quote(str(venv))}
INTELLIFOLD_VENV="$BOLTZ_VENV"
PROTENIX_VENV="$BOLTZ_VENV"
BOLTZ_MODEL_DIR="$NANOHUNTER_ROOT/models"
INTELLIFOLD_MODEL_DIR="$BOLTZ_MODEL_DIR"
PROTENIX_MODEL_DIR="$BOLTZ_MODEL_DIR"
PROTENIX_COMMON_DIR="$BOLTZ_MODEL_DIR/common"
PROTENIX_CONSTRAINT_MODEL_DIR="$BOLTZ_MODEL_DIR/constraint"
INTELLIFOLD_REPO="$NANOHUNTER_ROOT/repo"
PROTENIX_REPO="$INTELLIFOLD_REPO"
INTELLIFOLD_STUDIO_PATCH="$NANOHUNTER_ROOT/patch"
PROTENIX_STUDIO_PATCH="$INTELLIFOLD_STUDIO_PATCH"
BOLTZ_LOCK="$INTELLIFOLD_STUDIO_PATCH"
INTELLIFOLD_LOCK="$BOLTZ_LOCK"
PROTENIX_LOCK="$BOLTZ_LOCK"
VERIFIED_DOWNLOADER="$BOLTZ_LOCK"
PYTHON_BIN="$BOLTZ_VENV/bin/python"
INTELLIFOLD_PYTHON_BIN="$PYTHON_BIN"
PYTHON_312_VERSION=fixture
BOLTZ_VERSION=fixture
INTELLIFOLD_REV=fixture
INTELLIFOLD_RUNTIME_VERSION=fixture
PROTENIX_REV=fixture
PROTENIX_RUNTIME_VERSION=fixture
WITH_BOLTZ=1
WITH_BOLTZ_AFFINITY=1
WITH_INTELLIFOLD=1
WITH_INTELLIFOLD_FULL=1
WITH_PROTENIX_RUNTIME=1
WITH_PROTENIX_V2=1
WITH_PROTENIX_MINI=0
ensure_python() {{ :; }}
ensure_pinned_repo() {{ :; }}
git() {{ return 0; }}
seed_shared_protenix_common() {{ :; }}
activate_shared_protenix_common() {{ :; }}
install_pinned_kalign() {{ :; }}
begin_versioned_venv() {{ TRANSACTION_VENV="$3"; TRANSACTION_REUSED=1; }}
commit_versioned_venv() {{ touch base-committed; }}
write_component_receipt() {{ echo "$1" >> receipts; }}
download_verified_artifact() {{
 case "$2" in *boltz2_aff.ckpt|*intellifold_v2.pt) fail "Fixture host unavailable" ;; esac
 printf fixture > "$2"
}}
'''
                helper_start = SETUP.index('  download_protenix() {')
                helper_end = SETUP.index('\n  }', helper_start) + 4
                body += SETUP[helper_start:helper_end] + '\n'
                for key in [base, extra]:
                    start = SETUP.index(f'install_{key}() {{')
                    end = SETUP.index('\nreturn 0\n}', start) + len('\nreturn 0\n}')
                    body += SETUP[start:end] + '\n'
                body += f'run_install_component {base} install_{base}\nrun_install_component {extra} install_{extra} {base}\n'
                body += 'later() { touch later-engine; }; run_install_component later later\nfinish_install_components\n'
                result = self.run_shell(body, root)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertTrue((path/'base-committed').exists(), result.stdout + result.stderr)
                self.assertTrue((path/'later-engine').exists())
                self.assertEqual((path/'receipts').read_text().splitlines(), [base])
                self.assertIn(f'NHSTATE|{base}|ok', result.stdout)
                self.assertIn(f'NHDONE|partial|{extra}', result.stdout)


if __name__ == '__main__':
    unittest.main()
