"""Actual ESMFold2 chemistry identity in an environment without Boltz."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/'nise')]
from rfd4.ligand_score import esm_ligand_manifest
from esmfold2_predict import ligand_atom_maps
from esmfold_runtime import convert_structure
from ligand_atoms import audit_atoms

class IdentityTests(unittest.TestCase):
    def test_native_map_preserves_charge_stereo_and_input_order_without_boltz(self):
        with patch.dict(sys.modules,{'boltz':None}):
            for smiles in ['CCCO','C[NH2+]C','C[C@H](O)C(=O)O','OC(C)C']:
                with self.subTest(smiles=smiles):
                    manifest=esm_ligand_manifest(smiles)
                    native=ligand_atom_maps([dict(kind='ligand',id='B',smiles=smiles)])['B']
                    self.assertEqual(manifest['smiles_used'],smiles)
                    self.assertEqual(manifest['atoms'],native['atoms'])
                    self.assertEqual(manifest,esm_ligand_manifest(smiles))
    def test_search_controller_uses_chemistry_runtime_but_protein_does_not(self):
        from rfd4.predictors import search_runtime_spec
        for engine in ("esmfold2-full-mlx","esmfold2-fast-mlx","esmfold2-600-mlx"):
            python,env=search_runtime_spec(Path("/runtime"),dict(task="ligand",predictor=engine))
            self.assertEqual(str(python),"/runtime/venvs/NanoHunter_rfd4/bin/python")
        python,_=search_runtime_spec(Path("/runtime"),dict(task="protein",predictor="esmfold2-full-mlx"))
        self.assertEqual(str(python),"/runtime/venvs/NanoHunter_esmfold2/bin/python")

    def test_export_and_audit_accept_only_exact_native_identity(self):
        import gemmi
        smiles='CCCO';manifest=esm_ligand_manifest(smiles)
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'pred_min').mkdir();structure=gemmi.Structure();model=gemmi.Model('1');chain=gemmi.Chain('B');res=gemmi.Residue();res.name='LIG';res.seqid=gemmi.SeqId(1,' ')
            for i,row in enumerate(manifest['atoms']):
                atom=gemmi.Atom();atom.name=row['name'];atom.element=gemmi.Element(row['el']);atom.pos=gemmi.Position(i*1.5,0,0);res.add_atom(atom)
            chain.add_residue(res);model.add_chain(chain);structure.add_model(model);structure.make_mmcif_document().write_file(str(root/'pred_min/model_0.cif'))
            mapping=ligand_atom_maps([dict(kind='ligand',id='B',smiles=smiles)])
            (root/'ligand_atom_map.json').write_text(json.dumps(mapping))
            convert_structure(root,root/'ligand.pdb',manifest);audit_atoms(root/'ligand.pdb',manifest)
            mapping['B']['atoms'][0]['el']='N';(root/'ligand_atom_map.json').write_text(json.dumps(mapping))
            with self.assertRaisesRegex(ValueError,'identity mismatch'):convert_structure(root,root/'bad.pdb',manifest)
if __name__=='__main__':unittest.main()
