"""Retain required static geometry data, exclude weights and Finder metadata."""
import json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/portable_runtimes_v1';sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import digest,verify
from runtime_view import clone_file
names=('new_ideal_coords.pt','new_ideal_bond_lengths.pt','new_ideal_bond_angles.pt','rotamer_alignment.pt','ideal_aa_coords_prot.pt','ligandmpnn_training_pdb_codes.pt','ligandmpnn_validation_pdb_codes.pt','ligandmpnn_test_sm_pdb_codes.pt')
for engine in ('lasermpnn','openfold3','psichic'):
 src=OUT/(engine+'-release-final2');dest=OUT/(engine+'-release-final3');shutil.copytree(src,dest,symlinks=True,copy_function=clone_file);m=json.loads((dest/'runtime.json').read_text())
 for name in list(m['files']):
  if Path(name).name=='.DS_Store':(dest/name).unlink();del m['files'][name]
 if engine=='lasermpnn':
  source=Path.home()/'.iproteinstudio/src/LASErMPNN';m['static_data_files']=[]
  for name in names:
   rel='sources/LASErMPNN/files/'+name;p=dest/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/'files'/name,p);m['files'][rel]=dict(size=p.stat().st_size,sha256=digest(p));m['static_data_files'].append(rel)
  m['static_data_provenance']=dict(commit='5df210fced6764d83f01425d1fc4319a22b70c2a',purpose='Ideal residue coordinates/bonds/rotamer indices and dataset split identifiers; not learned parameters')
 (dest/'runtime.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');verify(dest)
 subprocess.run([sys.executable,str(ROOT/'tools/archive_runtime_package.py'),str(dest),'--output',str(OUT/'github-final3')],check=True)
 print(engine,'FINAL3',flush=True)
