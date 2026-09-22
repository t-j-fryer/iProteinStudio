#!/usr/bin/env python3
"""Create an immutable GitHub-Release candidate; never upload or overwrite assets."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import verify,digest
p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
m=verify(a.package);identity=digest(a.package/'runtime.json')
a.output.mkdir(parents=True,exist_ok=True);archive=a.output/(m['engine']+'-'+identity[:20]+'-macos-arm64.tar.gz')
if archive.exists():raise SystemExit('Refusing to overwrite immutable release candidate: '+str(archive))
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
 for name in sorted(m['files']):tar.add(a.package/name,arcname=name,recursive=False)
 tar.add(a.package/'runtime.json',arcname='runtime.json',recursive=False)
record=dict(engine=m['engine'],archive=archive.name,archive_sha256=digest(archive),manifest_sha256=identity,bytes=archive.stat().st_size,python=m['python'],signed=m['signed'],notarized=m['notarized'],channel=m['channel'])
archive.with_suffix('.release.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
