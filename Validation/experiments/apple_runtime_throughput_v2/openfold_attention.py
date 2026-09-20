"""Experimental FP32 SDPA for OpenFold's already-scaled stock attention only."""
def sdpa(torch,query,key,value,biases,use_high_precision=False):
 # OpenFold _prep_qkv already scales Q. Scaling again changes the model.
 if any(t.dtype!=torch.float32 for t in (query,key,value,*biases)):
  raise RuntimeError('This experiment only validates existing FP32 attention')
 if query.shape[-1]!=key.shape[-1] or query.shape[-1]!=value.shape[-1]:
  raise RuntimeError('This OpenFold experiment requires equal Q/K/V head widths; Torch2.6 MPS does not safely handle unequal V width')
 bias=None
 for b in biases:bias=b if bias is None else bias+b
 if max(query.ndim,key.ndim,value.ndim)>4:
  # Torch2.6 MPS miscompiles higher-rank SDPA. Attention is independent across
  # every leading dimension, so flatten those into a supported 4D batch.
  batch=torch.broadcast_shapes(query.shape[:-2],key.shape[:-2],value.shape[:-2])
  nq,nk,d=query.shape[-2],key.shape[-2],query.shape[-1]
  q=query.expand(*batch,nq,d).reshape(-1,1,nq,d)
  k=key.expand(*batch,nk,d).reshape(-1,1,nk,d)
  v=value.expand(*batch,nk,d).reshape(-1,1,nk,d)
  mask=None if bias is None else bias.expand(*batch,nq,nk).reshape(-1,1,nq,nk)
  return torch.nn.functional.scaled_dot_product_attention(q,k,v,attn_mask=mask,dropout_p=0.0,is_causal=False,scale=1.0).reshape(*batch,nq,d)
 return torch.nn.functional.scaled_dot_product_attention(query,key,value,attn_mask=bias,dropout_p=0.0,is_causal=False,scale=1.0)

def oracle(torch,device):
 gen=torch.Generator(device='cpu').manual_seed(20260919);rows=[]
 for shape in ((1,4,16,24),(2,3,4,17,24)):
  q=torch.randn(shape,generator=gen);k=torch.randn((*shape[:-2],19,shape[-1]),generator=gen);v=torch.randn((*shape[:-2],19,shape[-1]),generator=gen)
  biases=[torch.randn((*shape[:-3],1,shape[-2],19),generator=gen),torch.zeros((*shape[:-2],1,19))]
  biases[-1][...,-1]=-1e9
  scores=q.double()@k.double().transpose(-1,-2)
  for b in biases:scores=scores+b.double()
  reference=torch.softmax(scores,-1)@v.double()
  result=sdpa(torch,q.to(device),k.to(device),v.to(device),[b.to(device) for b in biases]).cpu().double()
  relative=float(torch.linalg.vector_norm(result-reference)/torch.linalg.vector_norm(reference))
  if not torch.isfinite(result).all() or relative>1e-5:raise RuntimeError(f'SDPA independent FP64 oracle failed: {relative}')
  rows.append(dict(shape=list(shape),relative_l2=relative))
 return rows

def install(torch):
 from openfold3.core.model.primitives import attention
 evidence=dict(oracle=oracle(torch,'mps'),calls=0,shapes={},scale=1.0,precision='existing FP32')
 def call(query,key,value,biases,use_high_precision=False):
  evidence['calls']+=1;shape=str(list(query.shape));evidence['shapes'][shape]=evidence['shapes'].get(shape,0)+1
  return sdpa(torch,query,key,value,biases,use_high_precision)
 attention._attention=call
 return evidence
