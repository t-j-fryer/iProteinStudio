"""Real concurrent preflight, immutable identity, crash/retry and short registry locks."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0] = [str(PIPE / 'mcp'), str(PIPE / 'scripts')]
from iprotein_mcp import plans, broker, common
import runtime_view


def prepare(root, value=1):
    return plans._persist('fixture', 'demo', {'output': str(root/'projects/demo/run'), 'value': value},
                          ['inert'], 'apple_gpu_exclusive', [])


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, NANOHUNTER_ROOT=str(self.root), IPROTEINSTUDIO_AGENT_ROOT=str(self.root/'agent'))
        self.env.start(); self.addCleanup(self.env.stop)
        base = self.root/'components/control/versions/v1'; base.mkdir(parents=True)
        (base/'runtime.json').write_text(json.dumps(dict(schema_version=1, engine='control', contains_weights=False, files={})))
        (self.root/'components/control/current').symlink_to(base)

    def test_retry_reuses_view_without_recloning_models(self):
        first = prepare(self.root)
        with patch.object(runtime_view, 'build', side_effect=AssertionError('must reuse completed preparation')):
            again = prepare(self.root)
        self.assertEqual(first, again)
        self.assertEqual(len(list((self.root/'agent/runtime_views').iterdir())), 1)
        self.assertEqual(len(list((self.root/'agent/plans').glob('*.json'))), 1)

    def test_settings_and_code_changes_get_new_identities(self):
        first = prepare(self.root)
        changed = prepare(self.root, 2)
        scripts = self.root/'scripts';scripts.mkdir();(scripts/'fixture.py').write_text('new code')
        updated = prepare(self.root)
        self.assertEqual(len({p['id'] for p in [first,changed,updated]}),3)
        self.assertTrue(Path(first['prepared_runtime_view']['path']).is_dir())

    def test_corrupt_reference_is_rejected(self):
        first = prepare(self.root)
        index = next((self.root/'agent/plan_requests').glob('*.json'))
        value = json.loads(index.read_text()); value['sha256']='0'*64;index.write_text(json.dumps(value))
        with self.assertRaisesRegex(common.StudioError, 'digest mismatch'):prepare(self.root)
        self.assertTrue(Path(first['prepared_runtime_view']['path']).is_dir())

    def test_interrupted_preparation_can_be_retried(self):
        with patch.object(runtime_view,'build',side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):prepare(self.root)
        self.assertFalse(list((self.root/'agent/plan_requests').glob('*.json')))
        result = prepare(self.root)
        self.assertEqual(plans.load_plan(result['id'],result['sha256']),result)

    def test_concurrent_identical_requests_build_one_view(self):
        children=[subprocess.Popen([sys.executable,__file__,'--prepare',str(self.root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(4)]
        values=[]
        for child in children:
            out,err=child.communicate(timeout=20);self.assertEqual(child.returncode,0,err);values.append(json.loads(out))
        self.assertEqual(len({v['id'] for v in values}),1)
        self.assertEqual((self.root/'build_calls').read_text().splitlines(),['build'])
        self.assertEqual(len(list((self.root/'agent/runtime_views').iterdir())),1)

    def test_slow_verification_does_not_hold_registry_lock(self):
        plan=prepare(self.root)
        def verify(*args):
            with (common.agent_root()/'registry.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return plan
        with patch.object(broker,'load_plan',side_effect=verify), patch.object(broker,'_spawn',return_value={'id':'fixture'}):
            self.assertEqual(broker.start_job(plan['id'],plan['sha256']),{'id':'fixture'})

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--prepare':
        root=Path(sys.argv[2]);original=runtime_view.build
        def counted(*args,**kwargs):
            with (root/'build_calls').open('a') as h:h.write('build\n')
            time.sleep(.25)
            return original(*args,**kwargs)
        with patch.object(runtime_view,'build',side_effect=counted):print(json.dumps(prepare(root)))
    else:unittest.main()
