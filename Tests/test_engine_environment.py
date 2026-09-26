"""Run actual Bash engine-launch functions against inert Python fixtures."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh'
SOURCE = RUNNER.read_text()
HELPERS = SOURCE[SOURCE.index('studio_activate_engine() {'):SOURCE.index('# One implementation serves')]
MONITORED = 'run_boltz_predict_monitored() {' + SOURCE.split('run_boltz_predict_monitored() {', 1)[1].split('\nrun_intellifold_predict_monitored()', 1)[0]


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='studio-engine-launch-')
        self.root = Path(self.tmp.name)
        self.engine = self.root / 'portable runtime'
        (self.engine/'bin').mkdir(parents=True)
        (self.engine/'bin/python').symlink_to(sys.executable)
        (self.engine/'bin/python3').symlink_to(sys.executable)

    def tearDown(self):
        self.tmp.cleanup()

    def shell(self, body, env=None):
        return subprocess.run(['/bin/bash', '-c', 'set -euo pipefail\n'+HELPERS+body,
                               'fixture', str(self.engine), str(self.root)],
                              env=env, capture_output=True, text=True, timeout=20)

    def test_portable_selection_restores_outer_environment(self):
        result = self.shell('''
export PYTHONHOME='/outer/python home' VIRTUAL_ENV='/outer/venv'
saved_path="$PATH"
studio_activate_engine "$1"
[[ "$(command -v python)" == "$1/bin/python" ]]
[[ "${PYTHONHOME+x}" != x ]]
python -c 'print("portable interpreter ran")'
studio_deactivate_engine
[[ "$PATH" == "$saved_path" && "$PYTHONHOME" == '/outer/python home' && "$VIRTUAL_ENV" == '/outer/venv' ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('portable interpreter ran', result.stdout)
        self.assertFalse((self.engine/'bin/activate').exists())

    def test_unset_and_empty_values_are_restored(self):
        for setup, check in [('unset PYTHONHOME VIRTUAL_ENV', '[[ "${PYTHONHOME+x}${VIRTUAL_ENV+x}" == "" ]]'),
                             ('export PYTHONHOME="" VIRTUAL_ENV=""', '[[ "${PYTHONHOME+x}${VIRTUAL_ENV+x}" == xx && "$PYTHONHOME$VIRTUAL_ENV" == "" ]]')]:
            with self.subTest(setup=setup):
                r=self.shell(setup+'\nstudio_activate_engine "$1"\nstudio_deactivate_engine\n'+check)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_real_venv_matches_standard_activation_context(self):
        legacy=self.root/'legacy environment'
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(legacy)],check=True,capture_output=True)
        program='import json,os,sys; print(json.dumps(dict(prefix=sys.prefix,base=sys.base_prefix,executable=sys.executable,path=sys.path,virtual_env=os.environ.get("VIRTUAL_ENV"),python_home=os.environ.get("PYTHONHOME"))))'
        env=dict(os.environ);env.pop('PYTHONHOME',None);env.pop('VIRTUAL_ENV',None)
        command='python -c '+shlex.quote(program)
        reference=subprocess.run(['/bin/bash','-c','set -euo pipefail; source "$1/bin/activate"; '+command,'fixture',str(legacy)],env=env,capture_output=True,text=True,check=True)
        r=self.shell('studio_activate_engine '+shlex.quote(str(legacy))+'\n'+command,env=env)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout),json.loads(reference.stdout))

    def test_missing_interpreter_and_nested_switch_fail_without_mutation(self):
        for body in ['if studio_activate_engine "$2/missing"; then exit 90; fi',
                     'studio_activate_engine "$1"; saved_path="$PATH"; if studio_activate_engine "$1"; then exit 91; fi']:
            r=self.shell('saved_path="$PATH"\n'+body+'\n[[ "$PATH" == "$saved_path" ]]')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('ERROR:',r.stderr)

    def test_actual_boltz_calibration_launch_and_error_propagation(self):
        for exit_code in (0,7):
            with self.subTest(exit_code=exit_code):
                (self.root/'engine.py').write_text('from pathlib import Path\nPath(__file__).with_suffix(".called").write_text("yes")\nprint("inert engine entered", flush=True)\nraise SystemExit('+str(exit_code)+')\n')
                body=MONITORED+'''
BOLTZ_VENV="$1"
BOLTZ_CLI=("$1/bin/python" "$2/engine.py")
BOLTZ_EXTRA_FLAGS=(--seed 42)
get_system_available_kb() { echo 1024; }
get_process_physical_footprint_kb() { echo 0; }
saved_path="$PATH"
if run_boltz_predict_monitored "$2/input.yaml" "$2/boltz" "$2/peak.txt" 0; then rc=0; else rc=$?; fi
[[ "$PATH" == "$saved_path" ]]
printf 'fixture_exit=%s\\n' "$rc"
'''
                r=self.shell(body)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn('fixture_exit='+str(exit_code),r.stdout)
                self.assertTrue((self.root/'engine.called').exists())
                self.assertIn('inert engine entered',(self.root/'boltz/calibration_predict.log').read_text())

    def test_all_iterative_activation_sites_use_checked_helper(self):
        self.assertNotIn('source "${BOLTZ_VENV}/bin/activate"',SOURCE)
        import re
        self.assertEqual(len(re.findall(r'studio_activate_engine "\$\{[A-Z]+_VENV\}" \|\| return \$\?',SOURCE)),14)
        self.assertEqual(len(re.findall(r'^\s*studio_deactivate_engine$',SOURCE,re.M)),14)
        self.assertNotRegex(SOURCE,r'source .*bin/activate')


if __name__=='__main__':
    unittest.main()
