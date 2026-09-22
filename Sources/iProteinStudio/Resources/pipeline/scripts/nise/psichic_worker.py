#!/usr/bin/env python3
"""Experimental PSICHIC resident worker: safe MPS ESM batch8 + CPU graph16."""
import argparse,importlib,json,os,sys,time
from pathlib import Path
from psichic_contract import installation,asset_root,validate_installation,validate_scores,validate_sequence,sha256,PROTOCOL
from runtime import atomic

class Engine:
    def __init__(self,root):
        if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK')!='0':raise RuntimeError('PSICHIC requires disabled implicit MPS fallback')
        validate_installation(root);base=installation(root);assets=asset_root(root)
        sys.path.insert(0,str(base/'sources/PSICHIC'))
        import torch,esm
        from models.net import net
        from utils import ligand_init
        if not torch.backends.mps.is_available():raise RuntimeError('PSICHIC ESM requires Apple MPS')
        torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.set_grad_enabled(False)
        self.torch=torch;self.protein=importlib.import_module('utils.protein_init');self.ligand_init=ligand_init;self.ligands={}
        config=json.loads((assets/'config.json').read_text());degree=torch.load(assets/'degree.pt',map_location='cpu',weights_only=True)
        params=dict(config['params']);params.update(regression_head=True,classification_head=False,multiclassification_head=3,device='cpu')
        self.graph=net(degree['ligand_deg'],degree['protein_deg'],**params).float().eval()
        self.graph.load_state_dict(torch.load(assets/'model.pt',map_location='cpu',weights_only=True))
        checkpoint=assets/'esm2_t33_650M_UR50D.pt'
        # Only the official preflight-hashed ESM checkpoint includes trusted config objects.
        data=torch.load(checkpoint,map_location='cpu',weights_only=False)
        reg=torch.load(assets/'esm2_t33_650M_UR50D-contact-regression.pt',map_location='cpu',weights_only=False)
        self.esm,alphabet=esm.pretrained.load_model_and_alphabet_core(checkpoint.stem,data,reg)
        self.esm.float().eval().to('mps');self.converter=alphabet.get_batch_converter();torch.mps.synchronize()

    def score_many(self,items,smiles,seed):
        import numpy as np,pandas as pd
        from utils.dataset import ProteinMoleculeDataset
        from utils.utils import DataLoader,virtual_screening
        from psichic_esm import extract
        torch=self.torch
        for item in items:validate_sequence(item['sequence'])
        if smiles not in self.ligands:
            parsed=self.ligand_init([smiles])
            if set(parsed)!={smiles}:raise ValueError('PSICHIC rejected ligand SMILES')
            self.ligands.update(parsed)
        torch.manual_seed(seed);start=time.monotonic();features={}
        for sequence,e,c in extract(self.esm,self.converter,[i['sequence'] for i in items],8):
            if not torch.isfinite(e).all() or not torch.isfinite(c).all():raise RuntimeError('Nonfinite ESM features')
            edges,ew=self.protein.contact_map(c)
            features[sequence]=dict(seq=sequence,seq_feat=torch.from_numpy(self.protein.seq_feature(sequence)),token_representation=e.half(),num_nodes=len(sequence),num_pos=torch.arange(len(sequence)).reshape(-1,1),edge_index=edges,edge_weight=ew)
        torch.mps.synchronize();feature_seconds=time.monotonic()-start;start=time.monotonic()
        frame=pd.DataFrame([dict(ID=str(i),Protein=v['sequence'],Ligand=smiles) for i,v in enumerate(items)])
        dataset=ProteinMoleculeDataset(frame,{smiles:self.ligands[smiles]},features,device='cpu')
        loader=DataLoader(dataset,batch_size=16,shuffle=False,follow_batch=['mol_x','clique_x','prot_node_aa'])
        result=virtual_screening(frame.copy(),self.graph,loader,'',save_interpret=False,ligand_dict=self.ligands,device='cpu',save_cluster=False)
        if result.ID.tolist()!=frame.ID.tolist():raise RuntimeError('PSICHIC result identity mismatch')
        graph_seconds=time.monotonic()-start;saved=[]
        for item,row in zip(items,result.to_dict('records')):
            values=validate_scores({k:float(v) for k,v in row.items() if k.startswith('predicted_')})
            record=dict(scores=values,engine='psichic',experimental=True,protocol=PROTOCOL,device='mps-esm/cpu-graph',precision='float32',esm_batch_size=8,graph_batch_size=16,model_load_count=2,feature_seconds_batch=feature_seconds,graph_seconds_batch=graph_seconds,batch_candidates=len(items),sequence=item['sequence'],smiles=smiles)
            atomic(Path(item['directory'])/'affinity.json',record);saved.append(record)
        return saved

def serve(path):
    config=json.loads(path.read_text());queue=Path(config['queue']);output=Path(config['output']).resolve()
    def owned(p):
        p=Path(p).resolve()
        if output not in p.parents:raise ValueError('PSICHIC request escapes campaign')
        return p
    owned(queue);start=time.monotonic();engine=Engine(config['root'])
    atomic(queue/'ready.json',dict(protocol=PROTOCOL,device='mps-esm/cpu-graph',fallback=0,pid=os.getpid(),model_load_count=2,config_sha256=sha256(path),startup_seconds=time.monotonic()-start))
    while not (queue/'stop.json').exists():
        try:os.kill(config['owner_pid'],0)
        except ProcessLookupError:return
        for request_path in sorted((queue/'requests').glob('*.json')):
            response=queue/'responses'/request_path.name
            if response.exists():continue
            request=json.loads(request_path.read_text())
            try:
                if not 1<=len(request['items'])<=64:raise ValueError('PSICHIC request supports 1–64 candidates')
                for item in request['items']:owned(item['directory'])
                results=engine.score_many(request['items'],request['smiles'],config['seed'])
                atomic(response,dict(ok=True,request_id=request['request_id'],input_sha256=sha256(request_path),results=results))
            except Exception as e:
                atomic(response,dict(ok=False,request_id=request.get('request_id'),error=str(e)));raise
        time.sleep(.1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);serve(p.parse_args().config)
