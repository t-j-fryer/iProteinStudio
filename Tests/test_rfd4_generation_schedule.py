"""Execute production scheduling with a fake model; no GPU or weights required."""
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from rfd4 import generate
from rfd4.contract import atomic,seal,verify

class GenerationScheduleTests(unittest.TestCase):
    def run_case(self,optimized,first_then_full=False):
        with tempfile.TemporaryDirectory() as raw:
            out=Path(raw);atomic(out/'studio_job.json',{'id':'test'})
            cfg={'output':str(out),'settings':{'seed':42,'count':3,'optimized_kernels':optimized}}
            path=out/'config.json';atomic(path,cfg);calls=[]
            class Model:
                def eval(self):return self
                def requires_grad_(self,value):return self
            pipe=SimpleNamespace(transformer=Model(),vae=Model())
            loader=SimpleNamespace(from_pretrained=lambda *a,**k:SimpleNamespace(to=lambda *a:pipe))
            torch=SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda:True)),set_num_threads=lambda n:None,bfloat16='bf16',inference_mode=contextlib.nullcontext)
            def call(pipe,current,seed,directory,use_optimized):
                done=directory/'completed.json'
                if done.exists():return verify(done)
                calls.append((seed,use_optimized,current['annotated_cif']))
                directory.mkdir(parents=True,exist_ok=True)
                artifact=directory/'structure.cif';artifact.write_text(str(seed))
                row={'id':f'seed_{seed}','seed':seed};seal(done,row,[artifact]);return row
            # Distinct lengths/inputs must not cause hidden reference generation.
            def family(config,index):return dict(config,annotated_cif=f'length_{100+index}.cif')
            with patch.dict(sys.modules,{'torch':torch,'diffusers':SimpleNamespace(RFD4ProteinaPipeline=loader)}),patch.dict(os.environ,{'NANOHUNTER_ROOT':str(out)}),patch('rfd4.contract.family_config',side_effect=family),patch.object(generate,'call',side_effect=call):
                if first_then_full:generate.main(path,first_only=True)
                generate.main(path)
                self.assertEqual(calls,[(42,optimized,'length_100.cif'),(43,optimized,'length_101.cif'),(44,optimized,'length_102.cif')])
                self.assertFalse((out/'qualification').exists())
                self.assertEqual(verify(out/'generation_completed.json')['count'],3)
                generate.main(path) # completed units reused on restart
                self.assertEqual(len(calls),3)
                (out/'generation/seed_42/structure.cif').write_text('tampered')
                with self.assertRaises(ValueError):generate.main(path)
    def test_optimized_generates_only_requested_families(self):self.run_case(True)
    def test_standard_generates_only_requested_families(self):self.run_case(False)
    def test_smoke_expansion_and_resume_do_not_add_reference_calls(self):self.run_case(True,True)
if __name__=='__main__':unittest.main()
