"""Read-only deployed app, shared CLI/MCP and override verification."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import plistlib
import subprocess
import sys

repo = Path(__file__).resolve().parents[3]
root = Path.home() / '.iproteinstudio'
app = repo / 'build/iProteinStudio.app'
info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
assert (info['CFBundleShortVersionString'], info['CFBundleVersion']) == ('0.2.20', '66')
assert (root / 'mcp/MCP_VERSION').read_text().strip() == '38'
expected = json.loads((Path(__file__).parent / 'bundle-hashes.json').read_text())
for path, digest in expected.items():
    assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, path
sys.path.insert(0, str(root / 'scripts'))
sys.path.insert(0, str(root / 'mcp'))
import prediction_profiles
from iprotein_mcp.prediction_settings import normalize
engine = 'esmfold2-full-mlx'
os.environ.pop(prediction_profiles.ENV, None)
settings = prediction_profiles.profile(engine)
assert settings == dict(msa_depth=128, recycles=3, diffusion_steps=50)
assert normalize()[engine] == settings
frozen = normalize({engine: dict(msa_depth=128, recycles=20, diffusion_steps=100)})
prediction_profiles.activate(frozen)
assert prediction_profiles.profile(engine) == frozen[engine]
python = root / 'components/control/current/python/bin/python3'
doctor = json.loads(subprocess.check_output([str(python), str(root/'mcp/studioctl.py'), 'doctor'], text=True))
assert doctor['ok'] and doctor['bridge_version'] == '38'
result = dict(version='0.2.20', build=66, defaults=settings, frozen_override_preserved=True,
              hashes=expected, doctor=doctor)
(Path(__file__).parent / 'installed-verified.json').write_text(json.dumps(result, indent=2)+'\n')
print('Verified app66, MCP38, CLI Full3/50, all changed resource hashes, and frozen Full20/100 overrides.')
