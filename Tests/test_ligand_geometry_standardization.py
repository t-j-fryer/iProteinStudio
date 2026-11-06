"""Native Boltz mapping regressions using only declared synthetic molecules."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS / 'nise'),
               str(ROOT / 'Sources/iProteinStudio/Resources/rfd3')]
from ligand_atoms import resolve
from ligand_geometry_policy import atom_settings
import ligand_geometry as geometry


class StandardizationTests(unittest.TestCase):
    def test_native_protonation_and_reordering_preserve_selected_identity(self):
        from rdkit import Chem
        # Glycine and alanine exercise charge changes and canonical reordering.
        for smiles in ('[NH3+]CC(=O)[O-]', 'N[C@@H](C)C(=O)[O-]',
                       '[NH3+:7][CH2:8][C:9](=[O:10])[O-:11]'):
            with self.subTest(smiles=smiles):
                manifest = resolve(smiles)
                self.assertTrue(manifest['chemical_state_changed'])
                mapped = atom_settings(dict(exposed_atoms=[0]), smiles, manifest)
                target = Chem.MolFromSmiles(manifest['smiles_used'])
                nitrogen = next(a.GetIdx() for a in target.GetAtoms() if a.GetSymbol() == 'N')
                expected = next(a['name'] for a in manifest['atoms'] if a['index'] == nitrogen)
                self.assertEqual(mapped['exposed_atoms'], [expected])
                audit = mapped['atom_correspondence']
                self.assertTrue(audit['chemical_state_changed'])
                self.assertEqual(audit['input_to_manifest'][0], nitrogen)
                self.assertEqual(audit['boltz_parser_sha256'], manifest['boltz_parser_sha256'])

    def test_trace_labels_do_not_change_stereochemical_identity(self):
        from rdkit import Chem
        # Public free-biotin chemistry; no user/project molecule is read.
        # The labelled trace has different CIP ranks at two fused-ring centres.
        charged = 'O=C([O-])CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21'
        reference = Chem.MolFromSmiles(charged.replace('[O-]', 'O'))
        original = Chem.MolFromSmiles(charged)
        annotated = Chem.Mol(original)
        for atom in annotated.GetAtoms():
            atom.SetAtomMapNum(100 + atom.GetIdx())
        variants = (charged, Chem.MolToSmiles(annotated, canonical=False))
        for smiles in variants:
            with self.subTest(annotated=smiles != charged):
                manifest = resolve(smiles)
                before = json.dumps(manifest, sort_keys=True)
                mapped = atom_settings(dict(contact_atoms=list(range(7, 16)), exposed_atoms=[0]), smiles, manifest)
                target = Chem.MolFromSmiles(manifest['smiles_used'])
                expected = target.GetSubstructMatch(reference, useChirality=True)
                names = {a['index']: a['name'] for a in manifest['atoms']}
                self.assertEqual(mapped['hotspot_atoms'], [names[expected[i]] for i in range(7, 16)])
                self.assertEqual(mapped['exposed_atoms'], [names[expected[0]]])
                self.assertTrue(mapped['atom_correspondence']['chemical_state_changed'])
                self.assertEqual(json.dumps(manifest, sort_keys=True), before)

    def test_original_chemical_state_guard_remains_for_other_predictors(self):
        with self.assertRaisesRegex(ValueError, 'chemical state'):
            atom_settings(dict(contact_atoms=[0]), 'CC(=O)[O-]',
                          geometry.predicted_manifest('CC(=O)O', 'esmfold2-full-mlx'))

    def test_wrong_native_parser_or_changed_output_cannot_claim_correspondence(self):
        smiles = 'CC(=O)[O-]'
        manifest = resolve(smiles)
        for mutation in ({'boltz_parser_sha256': '0' * 64}, {'smiles_used': 'CCCO'},
                         {'input_smiles': 'CCCO'}, {'standardized': False}):
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'chemical state'):
                atom_settings(dict(contact_atoms=[0]), smiles, dict(manifest, **mutation))

    def test_ambiguous_selection_still_fails_after_standardization(self):
        smiles = 'CC(C)[NH3+]'
        manifest = resolve(smiles)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            atom_settings(dict(contact_atoms=[0]), smiles, manifest)
        mapped = atom_settings(dict(contact_atoms=[0, 2]), smiles, manifest)
        self.assertEqual(len(mapped['hotspot_atoms']), 2)
        self.assertEqual(mapped['atom_correspondence']['equivalent_matches'], 2)

    def test_native_trace_rejects_lost_labels_connectivity_and_stereochemistry(self):
        import boltz.data.parse.schema as schema
        from rdkit import Chem
        native = schema.standardize
        for change in ('labels', 'connectivity', 'stereo', 'inverted-stereo', 'bond-stereo'):
            smiles = 'C/C=C/C[NH3+]' if change == 'bond-stereo' else 'N[C@@H](C)C(=O)[O-]'
            manifest = resolve(smiles)
            def modified(value):
                result = native(value)
                molecule = Chem.MolFromSmiles(result)
                if not any(a.GetAtomMapNum() for a in molecule.GetAtoms()):
                    return result  # Real unlabelled parser output is unchanged.
                if change == 'labels':
                    molecule.GetAtomWithIdx(0).SetAtomMapNum(0)
                elif change == 'inverted-stereo':
                    next(a for a in molecule.GetAtoms() if a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED).InvertChirality()
                elif change in ('stereo', 'bond-stereo'):
                    Chem.RemoveStereochemistry(molecule)
                else:
                    edited = Chem.RWMol(molecule)
                    bond = edited.GetBondWithIdx(0)
                    edited.RemoveBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
                    molecule = edited.GetMol()
                return Chem.MolToSmiles(molecule)
            with self.subTest(change=change), patch.object(schema, 'standardize', modified):
                with self.assertRaisesRegex(ValueError, 'chemical state'):
                    atom_settings(dict(contact_atoms=[0]), smiles, manifest)

    def test_cli_accepts_native_state_change_and_reports_expected_errors_cleanly(self):
        command = [sys.executable, '-B', str(SCRIPTS / 'ligand_geometry.py'), 'validate',
                   '--smiles', 'CC(=O)[O-]', '--policy', json.dumps(dict(contact_atoms=[0]))]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['atom_correspondence']['chemical_state_changed'])
        # Reproduce the reported preflight through the actual CLI, including
        # the public multi-stereocentre regression and its Figure 4 core choices.
        charged_biotin = 'O=C([O-])CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21'
        passed = subprocess.run(command[:5] + [charged_biotin, '--policy', json.dumps(dict(
            mode='biotin-carboxamide-v1', contact_atoms=list(range(7, 16))))], capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)['valid'])
        failed = subprocess.run(command[:-1] + ['{}'], capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('Select at least one', failed.stderr)
        self.assertNotIn('Traceback', failed.stderr)

    def test_real_holo_receipt_records_native_mapping_and_preserves_source(self):
        for smiles in ('[NH3+]CC(=O)[O-]', 'O=C([O-])CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21'):
            with self.subTest(smiles=smiles):
                self.assert_holo_receipt(smiles)

    def assert_holo_receipt(self, smiles):
        import gemmi
        from ligand_preview import preview
        manifest = resolve(smiles)
        coordinates = preview(manifest['smiles_used'])['atoms']
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.cif'
            structure = gemmi.Structure(); structure.add_model(gemmi.Model('1'))
            for chain, residue_name, atoms in (
                ('A', 'ALA', [('CA', 'C', [30, 30, 30])]),
                ('B', 'LIG', [(a['name'], a['el'], p['xyz'])
                              for a, p in zip(manifest['atoms'], coordinates)])):
                c = gemmi.Chain(chain); r = gemmi.Residue()
                r.name = residue_name; r.seqid = gemmi.SeqId('1')
                if chain == 'B': r.het_flag = 'H'
                for name, element, xyz in atoms:
                    atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element(element)
                    atom.pos = gemmi.Position(*xyz); r.add_atom(atom)
                c.add_residue(r); structure[0].add_chain(c)
            structure.make_mmcif_document().write_file(str(source))
            before = source.read_bytes()
            result = geometry.check(source, smiles, dict(exposed_atoms=[0]), manifest=manifest)
            self.assertTrue(result['passed'])
            self.assertTrue(result['settings']['atom_correspondence']['chemical_state_changed'])
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(geometry.check(source, smiles, dict(exposed_atoms=[0]), manifest=manifest), result)


if __name__ == '__main__':
    unittest.main()
