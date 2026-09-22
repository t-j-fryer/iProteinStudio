import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/portable_runtimes_v1'
for package in sorted(OUT.glob('*-release-v1')):
 if package.name=='antifold-release-v1':package=OUT/'antifold-release-v2'
 subprocess.run([sys.executable,str(ROOT/'tools/archive_runtime_package.py'),str(package),'--output',str(OUT/'github-release')],check=True)
