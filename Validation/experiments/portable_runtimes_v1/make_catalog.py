"""Seal actual archive digests into the application-owned download catalog."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/portable_runtimes_v1';scripts=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts';sys.path.insert(0,str(scripts))
from runtime_package import digest
from engine_registry import engines
packages={};chosen=[]
for package in sorted(OUT.glob('*-release-final2')):
 folder='github-final2'
 if (OUT/package.name.replace('-final2','-final3')).is_dir():package=OUT/package.name.replace('-final2','-final3');folder='github-final3'
 m=json.loads((package/'runtime.json').read_text());sha=digest(package/'runtime.json');meta=OUT/folder/(m['engine']+'-'+sha[:20]+'-macos-arm64.tar.release.json');d=json.loads(meta.read_text())
 archive=meta.with_name(d['archive']);assert digest(archive)==d['archive_sha256']
 mapping={k:v for entry in engines().values() if entry['component']==m['engine'] for k,v in entry['mappings'].items()}
 packages[m['engine']]=dict(url='https://github.com/t-j-fryer/iProteinStudio/releases/download/runtimes-2026.09.20-1/'+d['archive'],archive_sha256=d['archive_sha256'],manifest_sha256=sha,bytes=d['bytes'],minimum_macos=m['minimum_macos'],architecture='arm64',mappings=mapping)
 chosen.append(dict(package=str(package),archive_path=str(archive),metadata=str(meta),**d))
(scripts/'runtime_releases.json').write_text(json.dumps(dict(schema_version=1,channel='trusted-beta',release='runtimes-2026.09.20-1',packages=packages),indent=2)+'\n')
(OUT/'publication-assets.json').write_text(json.dumps(chosen,indent=2)+'\n');print('Catalog sealed:',len(packages),'archives;',sum(v['bytes'] for v in packages.values()),'bytes total')
