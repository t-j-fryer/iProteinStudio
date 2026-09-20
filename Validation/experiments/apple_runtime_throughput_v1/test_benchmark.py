import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from analyse import compare
from bench_worker import atomic, sha, extract
from coordinator import verify_completed, verify_seal

LIMITS=json.loads(Path(__file__).with_name('manifest.json').read_text())['acceptance']

class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
        self.pae=self.p/'a.npz';np.savez(self.pae,pae=np.zeros((4,4)))
        self.a=dict(sequence='AAAA',atom_identities=[['A',str(i),'ALA','CA'] for i in range(4)],
            ca=[[0,0,0],[1,0,0],[0,2,0],[0,0,3]],confidence=dict(complex_plddt=.8,ptm=.7),
            geometry=dict(errors=[],violations=[]),pae_path=str(self.pae),seconds=2)
    def test_rigid_rotation_translation_passes(self):
        b=copy.deepcopy(self.a);b['ca']=(np.array(b['ca'])@np.array([[0,-1,0],[1,0,0],[0,0,1]])+12).tolist()
        self.assertTrue(compare(self.a,b,LIMITS)['passed'])
    def test_coordinate_corruption_fails(self):
        b=copy.deepcopy(self.a);b['ca'][0][0]=10;self.assertFalse(compare(self.a,b,LIMITS)['passed'])
    def test_nan_fails(self):
        b=copy.deepcopy(self.a);b['ca'][0][0]=float('nan');self.assertFalse(compare(self.a,b,LIMITS)['passed'])
    def test_confidence_change_fails(self):
        b=copy.deepcopy(self.a);b['confidence']['ptm']+=.1;self.assertFalse(compare(self.a,b,LIMITS)['passed'])
    def test_pae_change_fails(self):
        b=copy.deepcopy(self.a);p=self.p/'b.npz';np.savez(p,pae=np.ones((4,4)));b['pae_path']=str(p)
        self.assertFalse(compare(self.a,b,LIMITS)['passed'])
    def test_identity_change_fails(self):
        b=copy.deepcopy(self.a);b['atom_identities'][0][0]='B';self.assertFalse(compare(self.a,b,LIMITS)['passed'])
    def test_new_break_fails_even_if_baseline_has_other_break(self):
        self.a['geometry']['violations']=[dict(chain='A',residue_1='1',residue_2='2',atoms='C-N')]
        b=copy.deepcopy(self.a);b['geometry']['violations'][0]['residue_1']='3'
        self.assertFalse(compare(self.a,b,LIMITS)['passed'])
    def test_completed_tampering_rejected(self):
        out=self.p/'output';out.mkdir();p=out/'data';p.write_text('original');req=self.p/'req';req.write_text('{}')
        atomic(out/'completed.json',dict(request_sha256=sha(req),files={'data':sha(p)}));verify_completed(out,req)
        p.write_text('altered')
        with self.assertRaises(RuntimeError):verify_completed(out,req)
    def test_runtime_added_file_rejected(self):
        root=self.p/'env';root.mkdir();p=root/'code';p.write_text('original');receipt=self.p/'seal'
        atomic(receipt,dict(root=str(root),files={'code':sha(p)}));verify_seal(receipt)
        (root/'extra').write_text('unsafe')
        with self.assertRaises(RuntimeError):verify_seal(receipt)
    def test_schedule_copy_preserves_scalar_values_and_rng(self):
        import torch
        import inspect
        import textwrap
        from equivalent_schedule import transform
        def sample():
            sigmas=torch.tensor([123.123,1e-4,0],dtype=torch.float32)
            gammas=torch.where(sigmas>1,.8,0.)
            sigmas_and_gammas = list(zip(sigmas[:-1], sigmas[1:], gammas[1:]))
            result=[]
            for sigma_tm,sigma_t,gamma in sigmas_and_gammas:
                sigma_tm, sigma_t, gamma = sigma_tm.item(), sigma_t.item(), gamma.item()
                result.append((sigma_tm,sigma_t,gamma))
            return result
        namespace={'torch':torch}
        exec(transform(textwrap.dedent(inspect.getsource(sample))),namespace)
        before=torch.get_rng_state().clone()
        self.assertEqual(sample(),namespace['sample']())
        self.assertTrue(torch.equal(before,torch.get_rng_state()))
        with self.assertRaises(RuntimeError):transform('def sample(): pass')

    def test_profile_preserves_result_and_records_calls(self):
        from types import SimpleNamespace
        from profile_stages import StageProfile
        def original(*a,**kw):return 'unchanged'
        torch=SimpleNamespace(mps=SimpleNamespace(synchronize=lambda:None),linalg=SimpleNamespace(svd=original))
        session=SimpleNamespace(model=SimpleNamespace(pairformer_module=SimpleNamespace(forward=original),
                    structure_module=SimpleNamespace(sample=original)),boltz_main=SimpleNamespace(process_inputs=original))
        profile=StageProfile(session,torch)
        self.assertEqual(session.model.pairformer_module.forward(1),'unchanged')
        self.assertEqual(session.model.structure_module.sample(1),'unchanged')
        self.assertEqual(profile.report()['stages']['pairformer_module']['calls'],1)
        profile.reset();self.assertEqual(profile.report()['stages'],{})

    def test_extract_real_coordinate_parser(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'Sources/iProteinStudio/Resources/pipeline/scripts'))
        import validate_prediction_geometry as geometry
        p=self.p/'structure.pdb'
        p.write_text('ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 80.00           C  \nEND\n')
        c=self.p/'confidence.json';atomic(c,dict(complex_plddt=.8,ptm=.7));pae=self.p/'one.npz';np.savez(pae,pae=np.zeros((1,1)))
        result=extract(p,c,pae,'A',geometry);self.assertEqual(result['sequence'],'A');self.assertEqual(len(result['ca']),1)
        with self.assertRaises(RuntimeError):extract(p,c,pae,'AA',geometry)

if __name__=='__main__':unittest.main()
