"""Actual CPU inference, same seed/model/input, across source and portable layouts."""
import json,os,runpy,sys
from pathlib import Path
req=json.loads(Path(sys.argv[1]).read_text());root=Path(req['root']);out=Path(req['output']);out.mkdir()
import numpy as np,torch,random
random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.set_num_threads(4)
if req['engine']=='mpnn':
 source=root/'src/LigandMPNN';model=req['model'];checkpoint={'protein_mpnn':'proteinmpnn_v_48_020.pt','soluble_mpnn':'solublempnn_v_48_020.pt','ligand_mpnn':'ligandmpnn_v_32_010_25.pt','abmpnn':'abmpnn.pt'}[model]
 kind='protein_mpnn' if model=='abmpnn' else model
 sys.path.insert(0,str(source));sys.argv=[str(source/'run.py'),'--model_type',kind,'--checkpoint_'+kind,str(source/'model_params'/checkpoint),'--pdb_path',req['fixture'],'--out_folder',str(out),'--seed','42','--batch_size','1','--number_of_batches','1','--save_stats','1']
 runpy.run_path(str(source/'run.py'),run_name='__main__')
else:
 source=root/'src/LASErMPNN';sys.path[:0]=[str(source.parent),str(source)]
 sys.argv=[str(source/'run_batch_inference.py'),req['fixture'],str(out),'1','--designs_per_batch','1','--device','cpu','--output_fasta_only','--model_weights_path',str(source/'model_weights/laser_weights_0p1A_nothing_heldout.pt')]
 runpy.run_path(str(source/'run_batch_inference.py'),run_name='__main__')
sequences=[]
for p in list(out.rglob('*.fa'))+list(out.rglob('*.fasta')):
 sequences += [line.strip() for line in p.read_text().splitlines() if line.strip() and not line.startswith('>')]
if not sequences or any(set(s)-set('ACDEFGHIKLMNPQRSTVWYX:/') for s in sequences):raise ValueError('Missing/invalid sampled sequences')
(out/'audit.json').write_text(json.dumps(dict(sequences=sequences,seed=42,model=req['model']),indent=2)+'\n')
