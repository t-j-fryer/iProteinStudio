"""Executing the bundled bridge must not modify signed resources."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp'


def inventory(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class ReadOnlyBundleTests(unittest.TestCase):
    def test_entry_points_preserve_resource_inventory(self):
        cases = [('studioctl.py', ['doctor']), ('server.py', ['--profile', 'read']),
                 ('remote_gateway.py', ['--help']), ('remote_server.py', ['--help']),
                 ('configure.py', ['--help'])]
        for name, arguments in cases:
            with self.subTest(entry=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); bridge = root / 'sealed-resources'
                shutil.copytree(MCP, bridge, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                before = inventory(bridge)
                env = dict(os.environ)
                for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE'):
                    env.pop(key, None)
                env.update(NANOHUNTER_ROOT=str(root/'runtime'), IPROTEINSTUDIO_AGENT_ROOT=str(root/'runtime/agent'))
                request = json.dumps({'jsonrpc':'2.0', 'id':1, 'method':'initialize', 'params':{}})+'\n'
                result = subprocess.run([sys.executable, str(bridge/name), *arguments], env=env,
                                        input=request, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                if name == 'studioctl.py': self.assertTrue(json.loads(result.stdout)['ok'])
                if name == 'server.py': self.assertIn('result', json.loads(result.stdout))
                self.assertEqual(before, inventory(bridge), name+' modified its signed resource directory')


if __name__ == '__main__':
    unittest.main()
