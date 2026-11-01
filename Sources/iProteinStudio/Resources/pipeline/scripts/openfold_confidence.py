"""Retain OpenFold's native PAE and score explicit protein pairs.

The upstream writer saves pLDDT/PDE but omits its already computed PAE matrix.
This callback adds output only; it never changes inference or confidence heads.
"""
import json
from pathlib import Path
import numpy as np


def save_interface_confidence(prefix, pae, asym_ids, atom_chain_ids, protein_ids):
    from ipsae_score import calculate_ipsae
    # Same asym-ID convention used by OF3OutputWriter.get_pae_confidence_scores.
    lookup={i+1:str(chain) for i,chain in enumerate(np.unique(atom_chain_ids))}
    ids=np.asarray(asym_ids).reshape(-1)
    if any(int(i) not in lookup for i in ids):raise ValueError('OpenFold PAE has an unknown chain identity.')
    chains=[lookup[int(i)] for i in ids]
    matrix=np.asarray(pae,dtype=float)
    if matrix.shape!=(len(chains),len(chains)) or not np.isfinite(matrix).all():
        raise ValueError('OpenFold native PAE/token mapping is incomplete or nonfinite.')
    prefix=Path(prefix)
    np.savez_compressed(str(prefix)+'_pae.npz',pae=matrix,token_chain_ids=np.asarray(chains))
    if len(protein_ids)>=2:
        metrics=calculate_ipsae(matrix,chains,protein_ids)
        summary=Path(str(prefix)+'_confidences_aggregated.json')
        values=json.loads(summary.read_text());values.update(metrics)
        summary.write_text(json.dumps(values,indent=2,allow_nan=False)+'\n')


def install(runner):
    """Wrap only this runner's native writer; keep native callbacks and settings."""
    from openfold3.core.runners.writer import OF3OutputWriter,_take_batch_dim,_take_sample_dim
    from types import MethodType
    writers=[c for c in runner.callbacks if isinstance(c,OF3OutputWriter)]
    if len(writers)!=1:raise ValueError('Expected one OpenFold native output writer.')
    writer=writers[0];native=writer.write_all_outputs
    writer.studio_protein_ids=[]
    def write_all_outputs(self,batch,outputs,confidence_scores):
        native(batch,outputs,confidence_scores)
        for b in range(outputs['atom_positions_predicted'].shape[0]):
            scores=_take_batch_dim(confidence_scores,b)
            asym=batch['asym_id'][b].detach().cpu().numpy()
            for sample in range(outputs['atom_positions_predicted'].shape[1]):
                current=_take_sample_dim(scores,sample)
                if 'pae' not in current:raise ValueError('OpenFold PAE head did not return its expected matrix.')
                query=batch['query_id'][b];seed=batch['seed'][b]
                prefix=Path(self.output_dir)/query/f'seed_{seed}'/f'{query}_seed_{seed}_sample_{sample+1}'
                save_interface_confidence(prefix,current['pae'],asym,batch['atom_array'][b].chain_id,self.studio_protein_ids)
    writer.write_all_outputs=MethodType(write_all_outputs,writer)
    return writer
