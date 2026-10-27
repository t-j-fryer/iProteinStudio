"""CPU-only strict key/shape and tokenizer checks; no learned inference."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from esmfold2_600 import remap_encoder, sanitize_fold
p=argparse.ArgumentParser();p.add_argument('--metadata',type=Path,required=True);a=p.parse_args()
import mlx.core as mx
from mlx_lm.models import esmfold2,esmc
mx.set_default_device(mx.cpu)
def read(name):return json.loads((a.metadata/name).read_text())
def placeholders(name):
 return {k:mx.zeros(tuple(v['shape']),dtype=mx.float32) for k,v in read(name).items() if k!='__metadata__'}
from esmfold2_600_model import Experimental600
fold=Experimental600(read('ESMFold2-600-config.json'))
fw=sanitize_fold(placeholders('ESMFold2-600-tensor-header.json'), esmfold2)
fold.load_weights(list(fw.items()),strict=True)
encoder=esmc.Model(esmc.ModelArgs.from_dict(read('encoder-pinned-config.json')))
ew=remap_encoder(placeholders('ESMplusplus_large-tensor-header.json'))
encoder.load_weights(list(ew.items()),strict=True)
vocab=read('encoder-pinned-tokenizer.json')['model']['vocab']
assert all(vocab.get(t)==i for i,t in enumerate(esmc.SEQUENCE_VOCAB))
print(json.dumps(dict(strict_fold_tensors=len(fw),strict_encoder_tensors=len(ew),tokenizer_matches=True,device='cpu',learned_inference=False)))
