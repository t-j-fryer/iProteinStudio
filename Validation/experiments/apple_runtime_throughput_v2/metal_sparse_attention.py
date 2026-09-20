"""Experimental Metal sparse attention without materialized gathered K/V buffers.
Independent implementation. FP32 attention arithmetic, original activation dtype
at the output/gate boundary. This is a numerical-tolerance experiment, not bitwise.
"""
import mlx.core as mx

SOURCE=r'''
uint row_head = threadgroup_position_in_grid.x;
uint row = row_head / H;
uint head = row_head % H;
uint lane = thread_index_in_simdgroup;
threadgroup float scores[KK];
float local_max = -INFINITY;
for (uint n=lane; n<KK; n+=32) {
    uint col = uint(indices[row*KK+n]);
    float dot = 0.0f;
    for (uint j=0; j<D; ++j) {
        float product = float(q[row*H*D+head*D+j])*float(k[col*H*D+head*D+j]);
        dot += PRESERVE ? float(T(product)) : product;
    }
    float s = (PRESERVE ? float(T(dot))/metal::sqrt(float(D)) : dot*metal::rsqrt(float(D))) + float(bias[(row*L+col)*H+head]);
    scores[n] = s;
    local_max = metal::max(local_max,s);
}
float max_score = simd_max(local_max);
float local_sum = 0.0f;
for (uint n=lane; n<KK; n+=32) {
    float p = metal::exp(scores[n]-max_score);
    scores[n] = p;
    local_sum += p;
}
float denominator = simd_sum(local_sum);
threadgroup_barrier(mem_flags::mem_threadgroup);
for (uint j=lane; j<D; j+=32) {
    float value = 0.0f;
    for (uint n=0; n<KK; ++n) {
        uint col = uint(indices[row*KK+n]);
        float probability = scores[n]/denominator;
        if (PRESERVE) probability = float(T(probability));
        float product = probability*float(v[col*H*D+head*D+j]);
        value += PRESERVE ? float(T(product)) : product;
    }
    uint offset = row*H*D+head*D+j;
    output[offset] = T(float(T(value))*float(gate[offset]));
}
'''
_kernel=None
def fused(q,k,v,g,B,idx,H,preserve=False):
 global _kernel
 L,c=q.shape;kk=idx.shape[-1];d=c//H
 assert c%H==0 and k.shape==v.shape==g.shape==q.shape
 assert B.shape==(L,L,H) and idx.shape[0]==L and 0<kk<=256
 if _kernel is None:
  _kernel=mx.fast.metal_kernel(name='iprotein_sparse_attention_v1',input_names=['q','k','v','gate','bias','indices'],output_names=['output'],source=SOURCE,compile_options={'math_mode':'safe'})
 return _kernel(inputs=[q,k,v,g,B,idx],template=[('T',q.dtype),('L',L),('H',H),('D',d),('KK',kk),('PRESERVE',int(preserve))],grid=(L*H*32,1,1),threadgroup=(32,1,1),output_shapes=[q.shape],output_dtypes=[q.dtype])[0]

def install(R):
 from rfd3_attention import oracle
 evidence=oracle(R._sparse_attn_single,candidate=fused);counts={'calls':0,'shapes':{}}
 def call(q,k,v,g,B,idx,H):
  counts['calls']+=1;key=f'{q.shape}/{idx.shape}/{q.dtype}';counts['shapes'][key]=counts['shapes'].get(key,0)+1
  return fused(q,k,v,g,B,idx,H)
 R._sparse_attn_single=call
 return dict(oracle=evidence,execution=counts,implementation='Direct neighbor loads in custom Metal; unchanged inputs and gate')
