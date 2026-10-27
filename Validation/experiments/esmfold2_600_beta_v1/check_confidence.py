"""Small CPU oracle check against installed Biohub experimental confidence math."""
import json,sys
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
import numpy as np
import torch
import mlx.core as mx
from esm.models.esmfold2.experimental import ConfidenceHead as Reference
from esmfold2_600_model import ExperimentalConfidence
mx.set_default_device(mx.cpu);torch.set_num_threads(1);torch.manual_seed(17)
cc=dict(min_dist=2.,max_dist=12.,distogram_bins=8,num_plddt_bins=10,num_pae_bins=8,folding_trunk=dict(n_layers=0))
cfg=dict(d_single=8,d_pair=16,inputs=dict(d_inputs=10),confidence_head=cc)
ref=Reference(NS(hidden_size=8,pairwise_hidden_size=16,single_inputs_size=10,confidence_head=NS(**cc,num_hidden_layers=0))).eval()
# The pinned MLX FoldingTrunk rounds its inputs to BF16 even with zero
# blocks. Match that explicit backend boundary in this isolated head oracle;
# this checks head arithmetic, not whole-model or trunk equivalence.
class ReferenceBackendBoundary(torch.nn.Module):
 def forward(self, pair, pair_attention_mask=None):
  return pair.to(torch.bfloat16).to(pair.dtype)
ref.folding_trunk=ReferenceBackendBoundary()
with torch.no_grad(): ref.plddt_weight.copy_(torch.randn_like(ref.plddt_weight)*.1)
model=ExperimentalConfidence(cfg);model.load_weights([(k,mx.array(v.detach().numpy())) for k,v in ref.state_dict().items()],strict=True)
inputs=dict(s_inputs=torch.randn(1,6,10),z=torch.randn(1,6,6,16),x_pred=torch.randn(1,12,3),
 distogram_atom_idx=torch.arange(0,12,2)[None,:],token_attention_mask=torch.ones(1,6),
 atom_to_token=torch.arange(6).repeat_interleave(2)[None,:],atom_attention_mask=torch.ones(1,12),
 asym_id=torch.tensor([[0,0,0,1,1,1]]),mol_type=torch.zeros(1,6,dtype=torch.long),
 relative_position_encoding=torch.randn(1,6,6,16),token_bonds_encoding=torch.randn(1,6,6,16))
with torch.no_grad(): expected=ref(**inputs)
actual=model(**{k:mx.array(v.numpy()) for k,v in inputs.items()});mx.eval(actual)
errors={}
for k in expected:
 if k=='pair_chains_iptm':continue # Synthyra intentionally uses mean-of-pairs instead.
 a=np.asarray(actual[k]);b=expected[k].numpy();errors[k]=float(np.max(np.abs(a-b)));np.testing.assert_allclose(a,b,rtol=2e-5,atol=2e-5,err_msg=k)
# Check Synthyra's explicit pair-average contract separately from Biohub's max-row variant.
logits=expected['pae_logits'];n=logits.shape[-1];centres=(torch.arange(n)+.5)*32/n
d0=1.24*(max(6,19)-15)**(1/3)-1.8;tm=(logits.softmax(-1)/(1+(centres/d0)**2)).sum(-1)
pair=torch.stack([torch.stack([tm[:,i*3:(i+1)*3,j*3:(j+1)*3].sum((1,2))/(9+1e-5) for j in range(2)],-1) for i in range(2)],1)
np.testing.assert_allclose(np.asarray(actual['pair_chains_iptm']),pair.numpy(),rtol=2e-5,atol=2e-5)
print(json.dumps(dict(passed=True,max_absolute_errors=errors,chain_pair_average_passed=True,backend='CPU synthetic features, zero confidence trunk blocks, explicit MLX BF16 boundary',full_model_parity=False)))
