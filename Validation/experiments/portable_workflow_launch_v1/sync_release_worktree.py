"""Copy only this task's files into the isolated release checkout."""
from pathlib import Path
import shutil,subprocess
root=Path(__file__).resolve().parents[3];target=root/'.worktrees/portable-launch-release'
files=['VERSION','BUILD_NUMBER','CHANGELOG.md','Tests/run.py','Tests/test_engine_environment.py','Tests/test_mcp_bridge.py','Tests/test_workflow_pipelines.py','Tests/test_rfd3_target_export.py','Tests/test_nise_objective.py','lab_book/0198-fix-portable-iterative-engine-launch.md','lab_book/0199-qualify-portable-workflow-launches.md','Validation/lab_book/0052-portable-workflow-launches.md']
changed=subprocess.check_output(['git','diff','--name-only','--','Sources'],cwd=root,text=True).splitlines();files+=changed
for folder in ['Validation/experiments/portable_workflow_launch_v1','lab_book/artifacts/0198-portable-activation']:
 files += [str(p.relative_to(root)) for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
for name in sorted(set(files)):
 src=root/name;dst=target/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
for name,ids in [('LAB_BOOK.md',['0198','0199']),('Validation/LAB_BOOK.md',['0052'])]:
 base=subprocess.check_output(['git','show','7d29499a:'+name],cwd=root,text=True)
 own=[line for line in (root/name).read_text().splitlines() if any(('/'+i+'-') in line for i in ids)]
 assert len(own)==len(ids),(name,own)
 # Append only owned rows, preserving every existing published index entry.
 (target/name).write_text(base.rstrip()+'\n'+ '\n'.join(own)+'\n')
print('Synced',len(set(files)),'task-owned files; unrelated research changes excluded')
