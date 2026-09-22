"""PSICHIC's last-layer ESM features and unchanged contact head in safe batches.

Only <=700-residue inputs: upstream's long-sequence stitching stays separate.
No attention approximation, mixed precision, or changed model parameters.
"""
def extract(model,converter,sequences,batch_size):
    import torch
    if batch_size<1 or any(not 0<len(s)<=700 for s in sequences):raise ValueError('Short-sequence ESM batch contract violated')
    device=next(model.parameters()).device
    for start in range(0,len(sequences),batch_size):
        chunk=sequences[start:start+batch_size]
        _,_,tokens=converter([(str(start+i),s) for i,s in enumerate(chunk)])
        # Blocking copy is required on MPS even for a small integer input.
        tokens=tokens.to(device,non_blocking=False)
        with torch.no_grad():result=model(tokens,repr_layers=[33],return_contacts=True)
        embeddings=result['representations'][33].float().cpu()
        contacts=result['contacts'].float().cpu()
        for i,s in enumerate(chunk):yield s,embeddings[i,1:len(s)+1].contiguous(),contacts[i,:len(s),:len(s)].contiguous()
