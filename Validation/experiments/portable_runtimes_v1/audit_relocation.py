"""Read immutable paired outputs, including Boltz's separate NPZ matrices."""
import argparse,importlib.util,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
sys.path[:0]=[str(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'),str(HERE.parent/'apple_runtime_throughput_v2')]
import analyse
# Preserve the established audit and add only the Boltz storage-format reader.
source=(HERE.parent/'apple_runtime_throughput_v2/analyse.py').read_text()
source=source[:source.index('def main(')] if 'def main(' in source else source
source=source.replace(" result.update(matrices=matrices,confidence=conf)",""" if engine=='boltz':
  for p in (unit/'prediction').rglob('*.npz'):
   if 'predictions' not in p.parts:continue
   arrays=np.load(p)
   for key in ('pae','pde'):
    if key in arrays:matrices[key]=arrays[key]
 result.update(matrices=matrices,confidence=conf)""")
namespace=dict(analyse.__dict__);exec(compile(source,str(HERE/'boltz_storage_reader'), 'exec'),namespace)
extract,compare=namespace['extract'],namespace['compare']
def audit(out):
 cfg=json.loads((out/'frozen/run.json').read_text());rows=[]
 for engine in dict.fromkeys(r['engine'] for r in cfg['blocks'] if not r.get('sequence_test')):
  if not all((out/(engine+'-'+arm)/'completed.json').exists() for arm in ('baseline','portable')):rows.append(dict(engine=engine,passed=False,pending=True));continue
  try:
   a=extract(out/(engine+'-baseline')/'unit_00',engine);b=extract(out/(engine+'-portable')/'unit_00',engine);r=compare(a,b,engine,cfg['limits']);r['engine']=engine
  except Exception as e:r=dict(engine=engine,passed=False,error=str(e))
  rows.append(r)
 for model in dict.fromkeys(r['model'] for r in cfg['blocks'] if r.get('sequence_test')):
  try:
   a=json.loads((out/(model+'-baseline')/'audit.json').read_text());b=json.loads((out/(model+'-portable')/'audit.json').read_text());r=dict(engine=model,passed=a==b,exact=a==b)
  except Exception as e:r=dict(engine=model,passed=False,error=str(e))
  rows.append(r)
 return dict(passed=all(r['passed'] for r in rows),pairs=rows)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=audit(a.run.resolve());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
