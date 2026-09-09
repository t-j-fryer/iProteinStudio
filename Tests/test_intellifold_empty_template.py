"""Execute the shipped launch lines under macOS Bash with empty/populated template arrays."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
class LaunchTests(unittest.TestCase):
    def test_native_launch_preserves_empty_and_populated_template_arguments(self):
        source=(ROOT/'Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh').read_text()
        lines=[l.strip() for l in source.splitlines() if l.strip().startswith('env ${template_environment')]
        self.assertEqual(len(lines),4)
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);fake=root/'python'
            fake.write_text('#!/usr/bin/env python3\nimport os,sys,json\nprint(json.dumps({"args":sys.argv[1:],"template":os.environ.get("IPROTEINSTUDIO_INTELLIFOLD_TEMPLATE_MANIFEST")}))\n');fake.chmod(0o755)
            for enabled in [False,True]:
                for line in lines:
                    script='set -euo pipefail\n'+ '\n'.join([
                        'template_environment=()', 'template_flags=()',
                        'INTELLIFOLD_EXTRA_FLAGS=(--model v2-flash)',
                        'INTELLIFOLD_OMP_NUM_THREADS=1','INTELLIFOLD_VECLIB_MAXIMUM_THREADS=1',
                        'INTELLIFOLD_RUNNER="runner with spaces.py"','yaml="input with spaces.yaml"',
                        'input_yaml="$yaml"','out_dir="output with spaces"',
                        'predict_log='+shlex.quote(str(root/'prediction.log'))])+'\n'
                    if enabled:script+='template_environment=("IPROTEINSTUDIO_INTELLIFOLD_TEMPLATE_MANIFEST=template with spaces.json")\ntemplate_flags=(--use_template)\n'
                    result=subprocess.run(['/bin/bash'],input=script+line+'\nwait\n',text=True,capture_output=True,env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH']})
                    self.assertEqual(result.returncode,0,result.stderr)
                    record=json.loads((root/'prediction.log').read_text())
                    self.assertIn('input with spaces.yaml',record['args'])
                    self.assertEqual('--use_template' in record['args'],enabled)
                    self.assertEqual(record['template'],'template with spaces.json' if enabled else None)
if __name__=='__main__':unittest.main()
