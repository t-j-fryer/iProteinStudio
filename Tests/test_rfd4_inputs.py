"""Actual CPU molecule preparation, using the installed RFD4 runtime (no weights)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from rfd4.inputs import ligand_source

class InputTests(unittest.TestCase):
    def test_bonded_charged_aromatic_and_stereo_conformers(self):
        import gemmi
        from rdkit import Chem
        root=Path(os.environ['NANOHUNTER_ROOT'])
        for smiles in ['CCO','c1ccccc1','C[NH2+]C','C[C@H](O)C(=O)O']:
            with self.subTest(smiles=smiles),tempfile.TemporaryDirectory() as raw:
                p=ligand_source(root,smiles,raw);doc=gemmi.cif.read_file(str(p)).sole_block()
                molecule=Chem.MolFromSmiles(smiles)
                self.assertEqual(len(doc.find_values('_chem_comp_atom.atom_id')),molecule.GetNumAtoms())
                self.assertEqual(len(doc.find_values('_chem_comp_bond.value_order')),molecule.GetNumBonds())
                self.assertEqual(sum(map(int,doc.find_values('_chem_comp_atom.charge'))),Chem.GetFormalCharge(molecule))
                self.assertEqual(json.loads((Path(raw)/'molecule.json').read_text())['canonical_smiles'],Chem.MolToSmiles(molecule,True))
                if smiles=='c1ccccc1':self.assertTrue(all(x=='AROM' for x in doc.find_values('_chem_comp_bond.value_order')))
    def test_ambiguous_stereo_and_disconnected_molecules_rejected(self):
        root=Path(os.environ['NANOHUNTER_ROOT'])
        for smiles in ['CC(O)C(=O)O','CCO.CCO']:
            with self.subTest(smiles=smiles),tempfile.TemporaryDirectory() as raw,self.assertRaises(ValueError):
                ligand_source(root,smiles,raw)

if __name__=='__main__':unittest.main()
