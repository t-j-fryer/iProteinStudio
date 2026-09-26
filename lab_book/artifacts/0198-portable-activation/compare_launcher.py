"""Compare trusted released/current launchers using an inert portable layout."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
REL='Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh'
released=subprocess.check_output(['git','show','v0.2.6-beta:'+REL],cwd=ROOT,text=True)
current=(ROOT/REL).read_text()
records=[]
for label,source in [('released-0.2.6',released),('patched-source',current)]:
    function='run_boltz_predict_monitored() {'+source.split('run_boltz_predict_monitored() {',1)[1].split('\nrun_intellifold_predict_monitored()',1)[0]
    helpers=source[source.index('studio_activate_engine() {'):source.index('# One implementation serves')] if 'studio_activate_engine() {' in source else ''
    with tempfile.TemporaryDirectory(prefix='studio-activation-compare-') as tmp:
        root=Path(tmp);(root/'python/bin').mkdir(parents=True)
        (root/'python/bin/python').symlink_to(sys.executable)
        (root/'engine.py').write_text('from pathlib import Path\nPath(__file__).with_suffix(".called").write_text("yes")\nprint("inert engine entered", flush=True)\n')
        script='set -euo pipefail\n'+helpers+function+'''
BOLTZ_VENV="$1/python"
BOLTZ_CLI=("$1/python/bin/python" "$1/engine.py")
BOLTZ_EXTRA_FLAGS=(--seed 42)
get_system_available_kb() { echo 1024; }
get_process_physical_footprint_kb() { echo 0; }
if ! run_boltz_predict_monitored "$1/input.yaml" "$1/boltz" "$1/peak.txt" 0; then exit 81; fi
'''
        run=subprocess.run(['/bin/bash','-c',script,'fixture',str(root)],capture_output=True,text=True,timeout=20)
        records.append(dict(source=label,runner_sha256=hashlib.sha256(source.encode()).hexdigest(),exit_code=run.returncode,engine_invoked=(root/'engine.called').exists(),log_created=(root/'boltz/calibration_predict.log').exists(),output_directory_created=(root/'boltz').is_dir(),stderr=run.stderr.replace(str(root),'<fixture>')))
assert records[0]['exit_code']!=0 and not records[0]['engine_invoked'] and not records[0]['log_created']
assert records[1]['exit_code']==0 and records[1]['engine_invoked'] and records[1]['log_created']
Path(__file__).with_name('launcher-comparison.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))
