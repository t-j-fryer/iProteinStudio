"""Real Boltz parsing, chemical identity, per-atom SASA and selection tests.

Run with the installed Boltz Python. No model inference or downloads.
"""
import json
import os
from pathlib import Path
import pickle
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rdkit.Chem import Descriptors  # Match Boltz CLI import order before AllChem.
from rdkit import Chem
from boltz.data.parse.schema import parse_boltz_schema
import gemmi
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts/nise'))
os.environ.setdefault('NANOHUNTER_ROOT', str(ROOT))
import atom_geometry, contract, ligand_atoms, nise_lib, nise_run, rfd3_initial
from runtime import Backend


def pdb(path, manifest, protein_xyz, ligand_xyz=None, reverse=False):
    st = gemmi.Structure(); model = gemmi.Model('1')
    a = gemmi.Chain('A')
    for i, xyz in enumerate(protein_xyz):
        res = gemmi.Residue(); res.name = 'ALA'; res.seqid = gemmi.SeqId(i+1, ' ')
        atom = gemmi.Atom(); atom.name = 'CA'; atom.element = gemmi.Element('C'); atom.pos = gemmi.Position(*xyz)
        res.add_atom(atom); a.add_residue(res)
    b = gemmi.Chain('B'); res = gemmi.Residue(); res.name = 'LIG'; res.seqid = gemmi.SeqId(1, ' '); res.het_flag = 'H'
    pairs = list(zip(manifest['atoms'], ligand_xyz or [[x['x'], x['y'], x['z']] for x in manifest['atoms']]))
    if reverse: pairs.reverse()
    for entry, xyz in pairs:
        atom = gemmi.Atom(); atom.name = entry['name']; atom.element = gemmi.Element(entry['el']); atom.pos = gemmi.Position(*xyz)
        res.add_atom(atom)
    b.add_residue(res); model.add_chain(a); model.add_chain(b); st.add_model(model); st.write_pdb(str(path))


class AtomTests(unittest.TestCase):
    def settings(self, manifest, **kwargs):
        return contract.normalize(dict(smiles=manifest['input_smiles'], ligand_atom_signature=manifest['signature'],
            ligand_atoms_generated_for=manifest['input_smiles'], **kwargs))

    def test_names_match_real_boltz_affinity_parser(self):
        for smiles in ['CCO', 'CC[NH3+]', 'CC(=O)[O-]', 'N[C@@H](C)C(=O)O', 'Oc1ccc2ccccc2c1',
                       'O=C(NCCO)c1ccc(-c2c3ccc(=O)cc-3oc3cc([O-])ccc23)c(C(=O)[O-])c1']:
            with self.subTest(smiles=smiles), tempfile.TemporaryDirectory() as raw:
                mapping = ligand_atoms.resolve(smiles)
                parsed = parse_boltz_schema('ligand', dict(version=1, sequences=[dict(ligand=dict(id='B', smiles=smiles))],
                    properties=[dict(affinity=dict(binder='B'))]), {}, Path(raw), boltz_2=True)
                self.assertEqual(list(parsed.structure.atoms['name']), mapping['input_order_names'])
                self.assertEqual(len(set(mapping['input_order_names'])), len(mapping['atoms']))
                self.assertEqual(ligand_atoms.resolve(smiles)['signature'], mapping['signature'])
        self.assertTrue(ligand_atoms.resolve('CC[NH3+]')['chemical_state_changed'])

    def test_selected_contacts_are_accepted_by_real_boltz_parser(self):
        import yaml
        mapping = ligand_atoms.resolve('CC[NH3+]')
        ccd_path = Path(os.environ['NANOHUNTER_ROOT']) / 'models/boltz2/mols/ALA.pkl'
        with ccd_path.open('rb') as stream:
            alanine = pickle.load(stream)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root/'query.yaml'
            contacts = [["B", a['name']] for a in mapping['atoms']]
            nise_lib.write_boltz_yaml(source, 'AAA', mapping['smiles_used'], affinity=True,
                                     pocket=dict(binder='A', contacts=contacts, max_distance=6, force=True))
            parsed = parse_boltz_schema('query', yaml.safe_load(source.read_text()), {'ALA': alanine}, root, boltz_2=True)
            self.assertEqual(list(parsed.structure.atoms['name'])[-3:], mapping['input_order_names'])

    def test_standardization_failure_never_falls_back(self):
        with patch('boltz.data.parse.schema.standardize', return_value=None):
            with self.assertRaisesRegex(ValueError, 'standardization failed'):
                ligand_atoms.resolve('CCO')

    def test_selection_invalidated_by_state_or_map_change(self):
        mapping = ligand_atoms.resolve('CCO')
        selected = self.settings(mapping, hotspot_atoms=[mapping['atoms'][0]['name']])
        ligand_atoms.validate_selection(selected, mapping)
        with self.assertRaisesRegex(ValueError, 'stale'):
            ligand_atoms.validate_selection(dict(selected, ligand_atom_signature='0'*64), mapping)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            ligand_atoms.validate_selection(dict(selected, hotspot_atoms=['C999']), mapping)
        for change in [dict(exposed_atoms=selected['hotspot_atoms']), dict(smiles='CCN'), dict(exposure_min_fraction=0),
                       dict(hotspot_atoms=['C1','C1']), dict(hotspot_distance=True)]:
            with self.assertRaises(ValueError): contract.normalize(dict(selected, **change))
        self.assertNotIn(mapping['atoms'][0]['name'], ligand_atoms.contact_atoms(mapping, excluded=selected['hotspot_atoms']))

    def test_exposed_vs_buried_ligand_and_hotspot_distance(self):
        mapping = ligand_atoms.resolve('CCO'); name = mapping['atoms'][0]['name']
        ligand_xyz = [[0,0,0], [1.5,0,0], [2.8,0,0]]
        settings = self.settings(mapping, exposed_atoms=[name])
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw)/'complex.pdb'
            pdb(path, mapping, [[30,0,0], [30,5,0], [30,0,5]], ligand_xyz)
            check = atom_geometry.measure(path, settings, mapping)
            self.assertTrue(check['passed']); self.assertAlmostEqual(check['exposure'][name]['retained_fraction'], 1)
            shell = [[3*x,3*y,3*z] for x in [-1,0,1] for y in [-1,0,1] for z in [-1,0,1] if (x,y,z)!=(0,0,0)]
            pdb(path, mapping, shell, ligand_xyz)
            check = atom_geometry.measure(path, settings, mapping)
            self.assertFalse(check['passed']); self.assertLess(check['exposure'][name]['retained_fraction'], .5)
            self.assertTrue(atom_geometry.measure(path, self.settings(mapping, hotspot_atoms=[name]), mapping)['passed'])
            pdb(path, mapping, [[30,0,0], [30,5,0], [30,0,5]], ligand_xyz)
            self.assertFalse(atom_geometry.measure(path, self.settings(mapping, hotspot_atoms=[name]), mapping)['passed'])

    def test_reordered_ligand_atoms_keep_correspondence_but_changed_identity_fails(self):
        mapping = ligand_atoms.resolve('CCO')
        with tempfile.TemporaryDirectory() as raw:
            p, q = Path(raw)/'p.pdb', Path(raw)/'q.pdb'
            protein = [[4,0,0],[4,4,0],[4,0,4]]
            pdb(p,mapping,protein); pdb(q,mapping,protein,reverse=True)
            ligand_atoms.audit_atoms(q,mapping)
            self.assertLess(nise_lib.self_consistency(p,q).ligand_rmsd, .001)
            q.write_text(q.read_text().replace(mapping['atoms'][0]['name'].rjust(4), ' C99'))
            with self.assertRaises(ValueError): ligand_atoms.audit_atoms(q,mapping)
            with self.assertRaises(ValueError): nise_lib.self_consistency(p,q)

    def test_failed_requirements_cannot_advance_and_remain_audited(self):
        mapping = ligand_atoms.resolve('CCO'); name = mapping['atoms'][0]['name']
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); path=root/'candidate.pdb'
            pdb(path,mapping,[[30,0,0],[30,5,0],[30,0,5]])
            backend=Backend(root,root,self.settings(mapping,hotspot_atoms=[name]),root)
            backend.ligand_manifest=mapping
            pred=SimpleNamespace(name='c01_t000_n00_s00',pdb=str(path),ligand_plddt=90,pbind=.9)
            args=SimpleNamespace(backend=backend,rank_metric='ligand_plddt+pbind',ligand_sasa_max=None)
            with patch.object(nise_lib,'self_consistency',return_value=SimpleNamespace(ca_rmsd=0,ligand_rmsd=0,ok=True)):
                selected=nise_run.evaluate_candidates({pred.name:pred},{pred.name:'A'*3},{pred.name:str(path)},args,1,2.5,2.5)
            self.assertEqual(selected,[])
            row=json.loads(next((root/'candidates').glob('*.json')).read_text())
            self.assertFalse(row['passed']); self.assertFalse(row['atom_checks']['passed'])
            backend.write_summary({})
            self.assertIn(pred.name,(root/'atom_checks.csv').read_text())

    def test_rfd3_translation_uses_input_order_when_native_names_differ(self):
        import csv
        mapping = ligand_atoms.resolve('CCO')
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            (root/'atom_selections.json').write_text(json.dumps({'smiles':mapping['smiles_used']}))
            rows=[[a['index'],a['el'].upper()+str(i+100),a['el']] for i,a in enumerate(mapping['atoms'])]
            def write():
                with (root/'atom_map.csv').open('w') as stream:
                    writer=csv.writer(stream); writer.writerow(['rdkit_index','atom_name','element']); writer.writerows(rows)
            write()
            self.assertEqual(rfd3_initial.atom_translation(root,mapping),
                             {row[1]:a['name'] for row,a in zip(rows,mapping['atoms'])})
            rows[0][2]='N'; write()
            with self.assertRaisesRegex(ValueError,'elements'):
                rfd3_initial.atom_translation(root,mapping)

    def test_nesso_native_names_are_not_boltz_indices(self):
        mapping=ligand_atoms.resolve('CC[NH3+]')
        mol=Chem.MolFromSmiles(mapping['smiles_used'])
        def name_atoms(molecule):
            for atom, rank in zip(molecule.GetAtoms(), Chem.CanonicalRankAtoms(molecule)):
                atom.SetProp('name', atom.GetSymbol()+str(rank+1))
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            with (root/'native.pkl').open('wb') as stream: pickle.dump(mol,stream)
            identity=ligand_atoms.audit_nesso_ligand(mapping['smiles_used'],root,name_atoms)
            self.assertNotEqual([a['name'] for a in identity['atoms']],mapping['input_order_names'])
            with self.assertRaisesRegex(ValueError,'chemical graph'):
                ligand_atoms.audit_nesso_ligand('CCO',root,name_atoms)


if __name__ == '__main__': unittest.main()
