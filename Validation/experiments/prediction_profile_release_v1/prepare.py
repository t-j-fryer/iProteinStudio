"""Freeze acceptance code and preflight through the shared immutable broker."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
root = Path.home() / '.iproteinstudio'
out = REPO / 'Validation/output/prediction_profile_release_v1' / sys.argv[1]
out.mkdir(parents=True, exist_ok=False)
frozen = out / 'frozen'; frozen.mkdir()
resources = REPO / 'Sources/iProteinStudio/Resources'
ignore = shutil.ignore_patterns('__pycache__', '*.pyc')
shutil.copytree(resources / 'pipeline/scripts', frozen / 'scripts', ignore=ignore)
shutil.copytree(resources / 'rfd3_overlay', frozen / 'rfd3_overlay', ignore=ignore)
for name in ('run.py', 'worker.py', 'manifest.json'):
    shutil.copy2(HERE / name, frozen / name)
inventory = json.loads((REPO / 'Validation/output/paper_binder_matrix_v1/inventory.json').read_text())
rows = sorted((r for r in inventory['rows'] if r['target'] == 'SUMO'), key=lambda r: len(r['binder_sequence']))
target = next(v for v in inventory['targets'].values() if len(v['sequence']) == 96)
msa = frozen / 'full.a3m'; shutil.copy2(target['source'], msa)
engines = {
    'boltz': 'NanoHunter_boltz', 'intellifold': 'NanoHunter_intellifold', 'intellifold-full': 'NanoHunter_intellifold',
    'protenix-mini': 'NanoHunter_protenix', 'protenix-v2': 'NanoHunter_protenix',
    'protenix-constraint-v0.5': 'NanoHunter_protenix_constraint', 'openfold-3-mlx': 'NanoHunter_openfold3_mlx',
    'esmfold2-fast-mlx': 'NanoHunter_esmfold2', 'esmfold2-full-mlx': 'NanoHunter_esmfold2'}
configuration = dict(output=str(out), engines=engines, rows=[rows[0], rows[len(rows)//3]], sequence=target['sequence'],
                     msa=str(msa), msa_sha256=hashlib.sha256(msa.read_bytes()).hexdigest())
if len(sys.argv) > 2 and sys.argv[2] == 'standalone':
    engines = {key: value for key, value in engines.items()
               if key in ('boltz', 'protenix-mini', 'protenix-v2', 'protenix-constraint-v0.5')}
    configuration.update(engines=engines, rows=[rows[0]], route='standalone')
(frozen / 'config.json').write_text(json.dumps(configuration, indent=2) + '\n')
os.environ['NANOHUNTER_ROOT'] = str(root)
sys.path.insert(0, str(root / 'mcp'))
from server import MCPServer
(out / 'workflow_guide.json').write_text(json.dumps(MCPServer('read').tool_call('workflow_guide', {'workflow': 'prediction'}), indent=2))
from iprotein_mcp.plans import _persist, _script_provenance
python = root / 'components/control/current/python/bin/python3'
command = ['/usr/bin/caffeinate', '-dimsu', str(python), str(frozen / 'run.py'), str(frozen / 'config.json')]
normalized = dict(workflow='runtime_benchmark', engines=list(engines),
                  runtime_python_paths=[str(root / 'venvs' / v / 'bin/python') for v in set(engines.values())],
                  output=str(out), scheduler='Serial release acceptance under the shared GPU lease',
                  steps=[dict(stage='production-profile-smoke', command=command, cwd=str(out))])
files = [p for p in frozen.rglob('*') if p.is_file()]
plan = _persist('desktop_runtime_benchmark', 'paper-binder-matrix', normalized, command, 'apple_gpu_exclusive', _script_provenance(files))
(out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
print(json.dumps(dict(id=plan['id'], sha256=plan['sha256'], output=str(out))))
