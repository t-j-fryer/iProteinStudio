import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from openfold_confidence import save_interface_confidence

class ConfidenceTests(unittest.TestCase):
    def test_native_callback_keeps_sample_and_token_identity(self):
        import torch
        from types import SimpleNamespace,MethodType
        from openfold3.core.runners.writer import OF3OutputWriter
        from openfold_confidence import install
        with tempfile.TemporaryDirectory() as tmp:
            writer=OF3OutputWriter(Path(tmp),pae_enabled=True);calls=[]
            def native(self,batch,outputs,confidence_scores):
                calls.append(True)
                folder=self.output_dir/'q'/'seed_42';folder.mkdir(parents=True)
                for sample in [1,2]:(folder/f'q_seed_42_sample_{sample}_confidences_aggregated.json').write_text('{"ptm":0.8}')
            writer.write_all_outputs=MethodType(native,writer)
            wrapped=install(SimpleNamespace(callbacks=[writer]));wrapped.studio_protein_ids=['A','B']
            batch=dict(query_id=['q'],seed=[42],asym_id=torch.tensor([[1,1,2,2,3]]),atom_array=[SimpleNamespace(chain_id=np.array(['A','B','C']))])
            scores=dict(pae=torch.stack([torch.ones((5,5)),torch.full((5,5),2.)])[None])
            wrapped.write_all_outputs(batch,dict(atom_positions_predicted=torch.zeros((1,2,3,3))),scores)
            self.assertEqual(calls,[True])
            for sample,expected in [(1,.5),(2,.2)]:
                d=json.loads((Path(tmp)/'q'/'seed_42'/f'q_seed_42_sample_{sample}_confidences_aggregated.json').read_text())
                self.assertAlmostEqual(d['ipsae_min'],expected);self.assertEqual(d['ptm'],.8)

    def test_native_pae_preserved_and_ligand_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/'sample';summary=Path(str(prefix)+'_confidences_aggregated.json')
            summary.write_text('{"ptm":0.75}')
            pae=np.ones((5,5));pae[4,:]=29;pae[:,4]=29
            save_interface_confidence(prefix,pae,[1,1,2,2,3],['C','B','A','A','B'],['A','B'])
            scores=json.loads(summary.read_text())
            self.assertEqual(scores['ptm'],.75);self.assertEqual(set(scores['ipsae_pairs']),{'A:B'})
            self.assertEqual(scores['ipsae_min'],.5)
            with np.load(str(prefix)+'_pae.npz') as saved:
                np.testing.assert_array_equal(saved['pae'],pae)
                self.assertEqual(saved['token_chain_ids'].tolist(),['A','A','B','B','C'])
            with self.assertRaises(ValueError):save_interface_confidence(prefix,pae,[1,2],['A','B'],['A','B'])

if __name__=='__main__':unittest.main()
