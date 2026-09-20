import json
from pathlib import Path
import numpy as np
from crystal_compare import OUT,reference,extract,aligned,verify_complete

def main():
 for p in OUT.glob('openfold_msa_init_*/progress.json'):
  if not (p.parent/'completed.json').exists():continue
  allrows={};measurements=[]
  try:
   for arm,folder in json.loads(p.read_text()).items():
    folder=Path(folder);verify_complete(folder,folder.parent/(folder.name+'.request.json'));allrows[arm]=[]
    for item in json.loads((folder/'result.json').read_text())['rows']:
     d=extract(Path(item).parent,'openfold');allrows[arm].append(d);m=d['measurement'];ref,core,receipt=reference(m['name'],m['sequence'])
     measurements.append(dict(arm=arm,warmup=m['warmup'],seconds=m['seconds'],core_rmsd=aligned(np.array([ref[i] for i in core]),d['ca'][core])[0],mean_core_plddt=float(d['ca_plddt'][core].mean()),geometry_violations=len(d['breaks'])))
   pairs=[]
   for a,b in zip(allrows['reference'],allrows['variant'],strict=True):
    pairs.append(dict(coordinates_exact=np.array_equal(a['ca'],b['ca']),plddt_exact=np.array_equal(a['ca_plddt'],b['ca_plddt']),matrices_exact=all(np.array_equal(a['matrices'][k],b['matrices'][k]) for k in a['matrices']),matrix_max_absolute_delta={k:float(np.max(np.abs(a['matrices'][k]-b['matrices'][k]))) for k in a['matrices']},confidence_exact=a['confidence']==b['confidence'],core_delta=aligned(a['ca'][20:],b['ca'][20:])[0]))
   result=dict(measurements=measurements,pairs=pairs)
  except Exception as e:result=dict(audit_error=str(e))
  (p.parent/'qualification.json').write_text(json.dumps(result,indent=2)+'\n');print(p.parent.name,json.dumps(result))
if __name__=='__main__':main()
