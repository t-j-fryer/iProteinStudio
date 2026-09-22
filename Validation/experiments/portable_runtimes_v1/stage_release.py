"""Copy shipping app implementation/tests into a clean publication worktree.

Never writes the main checkout's files or index. Unrelated figures, experiments
and historical lab edits remain in the working checkout.
"""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];dest=ROOT/'.worktrees/portable-release';out=ROOT/'Validation/output/portable_runtimes_v1'
if (ROOT/'.git').is_file():raise SystemExit('Run staging from the primary checkout, not its publication worktree')
paths=subprocess.check_output(['git','ls-files','-m','-o','--exclude-standard'],cwd=ROOT,text=True).splitlines()
selected=[p for p in paths if p.startswith(('Sources/','Tests/','tools/'))]
selected += ['release/release_app.sh','docs/INSTALL_UNSIGNED_BETA.md','docs/CLI.md','docs/NISE.md','docs/PORTABLE_RUNTIME_IMPLEMENTATION.md','docs/DISTRIBUTION_AND_ACCELERATION_PLAN.md','docs/APPLE_SILICON_THROUGHPUT_PLAN.md','lab_book/0177-integrate-psichic-portable-runtimes.md','Validation/lab_book/0047-portable-runtime-qualification.md']
selected += [str(p.relative_to(ROOT)) for p in (ROOT/'Validation/experiments/portable_runtimes_v1').glob('*') if p.is_file() and p.suffix in ('.py','.json','.md','.c')]
for name in sorted(set(selected)):
 p=ROOT/name;target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
(out/'release-source-files.json').write_text(json.dumps(sorted(set(selected)),indent=2)+'\n')
(dest/'VERSION').write_text('0.2.1\n');(dest/'BUILD_NUMBER').write_text('44\n')
for name,entry in [('LAB_BOOK.md','\n- [0177 — Experimental PSICHIC and portable engine distribution](lab_book/0177-integrate-psichic-portable-runtimes.md)\n'),('Validation/LAB_BOOK.md','\n- [0047 — Portable runtime qualification](lab_book/0047-portable-runtime-qualification.md)\n')]:
 p=dest/name;s=p.read_text()
 if entry.strip() not in s:p.write_text(s+entry)
