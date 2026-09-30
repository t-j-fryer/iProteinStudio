"""Copy task-owned changes, preserving unrelated work in the canonical checkout."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
DEST = ROOT / '.worktrees/prediction-profiles-release'
files = subprocess.check_output(['git', 'diff', '--name-only', '--', 'Sources', 'Tests'], cwd=ROOT, text=True).splitlines()
files += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--', 'Sources', 'Tests'], cwd=ROOT, text=True).splitlines()
files += ['VERSION', 'BUILD_NUMBER', 'CHANGELOG.md', 'README.md', 'build_app.sh', 'docs/CLI.md',
          'docs/RESIDENT_INFERENCE.md', 'docs/PREDICTION_PROFILES.md', 'tools/pipeline-vendor-manifest.json']
project_ids = ['0228', '0229', '0230', '0231', '0232', '0233', '0234']
validation_ids = ['0060', '0061', '0062', '0063', '0064', '0065', '0066']
for directory, ids in [('lab_book', project_ids), ('Validation/lab_book', validation_ids)]:
    for prefix in ids:
        files += [str(p.relative_to(ROOT)) for p in (ROOT / directory).glob(prefix + '-*.md')]
for name in ('prediction_profile_release_v1', 'sumo_model_matrix_v1', 'sumo_model_matrix_exact_v1',
             'sumo_request_overhead_v1', 'paper_binder_matrix_v1', 'mac_intervention_baselines_v1',
             'mac_workstation_filtering_v1'):
    folder = ROOT / 'Validation/experiments' / name
    files += [str(p.relative_to(ROOT)) for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
for name in sorted(set(files)):
    source, target = ROOT / name, DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
for name, ids in [('LAB_BOOK.md', project_ids), ('Validation/LAB_BOOK.md', validation_ids)]:
    base = subprocess.check_output(['git', 'show', 'origin/main:' + name], cwd=ROOT, text=True)
    rows = [line for line in (ROOT / name).read_text().splitlines()
            if any('/' + prefix + '-' in line for prefix in ids) and line not in base]
    (DEST / name).write_text(base.rstrip() + '\n' + '\n'.join(rows) + '\n')
print('Copied', len(set(files)), 'task-owned files to', DEST)
