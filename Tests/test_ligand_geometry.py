"""Real CPU geometry/atom-map/replay checks; no inference or GPU access."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/'nise'),str(ROOT/'Sources/iProteinStudio/Resources/rfd3')]
import ligand_geometry as geometry
from ligand_geometry_policy import normalize,atom_settings
from ligand_preview import preview
from biotin_exit import REFERENCE


class GeometryTests(unittest.TestCase):
    def test_figure4_preset_maps_same_nine_atoms(self):
        manifest=geometry.predicted_manifest(REFERENCE,'boltz')
        preset=preview(REFERENCE)['figure4_preset']
        settings=atom_settings(preset,REFERENCE,manifest)
        self.assertEqual(set(settings['hotspot_atoms']),{'C31','S20','C29','C32','N24','C30','N23','O17','C21'})
        self.assertEqual(settings['hotspot_distance'],6.)
        self.assertEqual(preset['mode'],'biotin-carboxamide-v1')
        alternate='C(=O)(O)CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@H]12'
        other=atom_settings(preview(alternate)['figure4_preset'],alternate,manifest)
        self.assertEqual(set(other['hotspot_atoms']),set(settings['hotspot_atoms']))

    def test_invalid_policy_and_chemical_state_fail(self):
        self.assertIsNone(normalize(None))
        with self.assertRaises(ValueError):normalize({})
        with self.assertRaises(ValueError):normalize(dict(contact_atoms=[True]))
        with self.assertRaises(ValueError):normalize(dict(contact_atoms=[0],exposed_atoms=[0]))
        with self.assertRaises(ValueError):normalize(dict(contact_atoms=[0],contact_distance=float('nan')))
        with self.assertRaisesRegex(ValueError,'chemical state'):
            atom_settings(dict(contact_atoms=[0]),'CC(=O)[O-]',geometry.predicted_manifest('CC(=O)O','esmfold2-full-mlx'))

    def test_directed_split_and_3d_input_identity(self):
        a=preview('CCCO',1,2)
        self.assertEqual(a['split'],dict(core=[0,1],linker=[2,3]))
        self.assertEqual([v['element'] for v in a['atoms']],['C','C','C','O'])
        self.assertEqual(len(a['bonds']),3)
        with self.assertRaises(ValueError):preview('C1CC1',0,1)

    def test_saved_figure4_structures_match_classifier_and_cones(self):
        figures=ROOT/'manuscript/figures/figure5_exit_v1/source_data'
        if not figures.is_dir():self.skipTest('Private paper replay fixtures are not shipped in the public repository')
        historical=json.loads((figures/'representative_filter_audit.json').read_text())['representatives']
        for i,name in enumerate(('biotin_rfd3.pdb','biotin_ph.pdb')):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/name;shutil.copyfile(figures/name,source)
                before=geometry.digest(source)
                result=geometry.check(source,REFERENCE,preview(REFERENCE)['figure4_preset'])
                old=historical[i]['saved_result']
                self.assertEqual(result['linker_exit']['label'],old['linker_exit']['label'])
                self.assertEqual(result['cone']['counts']['wide'],old['linker_exit']['nominal_wide_exit'])
                self.assertEqual(sum(result['cone']['counts'].values()),old['linker_exit']['protocol']['nphi'])
                self.assertEqual(geometry.digest(source),before)
                # Existing NISE cone inspection verifies saved measurements and
                # replays display samples without calling the classifier.
                from biotin_exit import source_signature
                old_result={k:v for k,v in result.items() if k not in ('cone','policy','settings','structure','structure_sha256','scope','ligand_chain')}
                receipt=source.parent/'geometry_receipts'/'historical.json';receipt.parent.mkdir()
                receipt.write_text(json.dumps(dict(input=dict(structure_sha256=before,manifest=geometry.predicted_manifest(REFERENCE,'boltz'),implementation=dict(code_sha256=source_signature())),result=old_result,result_sha256=hashlib.sha256(json.dumps(old_result,sort_keys=True,allow_nan=False).encode()).hexdigest())))
                from unittest.mock import patch
                with patch('biotin_exit.classify',side_effect=AssertionError('reclassified')):
                    self.assertEqual(geometry.recorded_preview(source)['cone'],result['cone'])
                # Resume never executes the scientific classifier a second time.
                from unittest.mock import patch
                with patch('atom_geometry.measure',side_effect=AssertionError('recomputed')):
                    self.assertEqual(geometry.check(source,REFERENCE,preview(REFERENCE)['figure4_preset']),result)
                saved=json.loads(Path(str(source)+'.ligand_geometry.json').read_text())
                self.assertEqual(hashlib.sha256(saved['result_json'].encode()).hexdigest(),saved['result_sha256'])
                saved['result']['passed']=not saved['result']['passed']
                Path(str(source)+'.ligand_geometry.json').write_text(json.dumps(saved))
                with self.assertRaisesRegex(ValueError,'result changed'):geometry.check(source,REFERENCE,preview(REFERENCE)['figure4_preset'])

    def test_generic_contacts_exposure_and_missing_atoms(self):
        import gemmi
        from rdkit import Chem
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'complex.pdb'
            p=preview('CCO');m=geometry.predicted_manifest('CCO','esmfold2-full-mlx')
            st=gemmi.Structure();model=gemmi.Model('1');st.add_model(model);model=st[0]
            a=gemmi.Chain('A');r=gemmi.Residue();r.name='ALA';r.seqid=gemmi.SeqId('1')
            atom=gemmi.Atom();atom.name='CA';atom.element=gemmi.Element('C');atom.pos=gemmi.Position(30,30,30);r.add_atom(atom);a.add_residue(r);model.add_chain(a)
            b=gemmi.Chain('B');r=gemmi.Residue();r.name='LIG';r.het_flag='H';r.seqid=gemmi.SeqId('1')
            for row,identity in zip(p['atoms'],m['atoms']):
                atom=gemmi.Atom();atom.name=identity['name'];atom.element=gemmi.Element(identity['el']);atom.pos=gemmi.Position(*row['xyz']);r.add_atom(atom)
            b.add_residue(r);model.add_chain(b);st.write_pdb(str(path))
            result=geometry.check(path,'CCO',dict(contact_atoms=[0],exposed_atoms=[2]),predictor='esmfold2-full-mlx')
            self.assertFalse(result['passed']);self.assertEqual(len(result['failures']),1)
            self.assertIsNone(result['cone']);self.assertGreater(result['exposure'][m['atoms'][2]['name']]['retained_fraction'],.9)
            # The MCP result boundary ANDs the gate with prior verdicts and
            # fails missing requested evidence; disabling the policy preserves
            # the historical verdict.
            sys.path.insert(0,str(SCRIPTS.parent/'mcp'))
            from iprotein_mcp.ligand_geometry import apply
            config=Path(directory)/'rfd4_config.json'
            config.write_text(json.dumps(dict(settings=dict(ligand_geometry=dict(contact_atoms=[0],exposed_atoms=[2])))))
            self.assertFalse(apply(directory,dict(is_hit=True),path.name)['is_hit'])
            positive=Path(directory)/'exposed.pdb';shutil.copyfile(path,positive)
            geometry.check(positive,'CCO',dict(exposed_atoms=[2]),predictor='esmfold2-full-mlx')
            self.assertTrue(apply(directory,dict(is_hit=True),positive.name)['is_hit'])
            self.assertFalse(apply(directory,dict(is_hit=False),positive.name)['is_hit'])
            self.assertFalse(apply(directory,dict(is_hit=True),'missing.pdb')['is_hit'])
            config.write_text(json.dumps(dict(settings={})))
            self.assertTrue(apply(directory,dict(is_hit=True),path.name)['is_hit'])
            Path(str(path)+'.ligand_geometry.json').unlink()
            model['B'][0].remove_atom(m['atoms'][0]['name'],'\x00',gemmi.Element('C'));st.write_pdb(str(path))
            with self.assertRaisesRegex(ValueError,'atom names/elements'):geometry.check(path,'CCO',dict(contact_atoms=[0]),predictor='esmfold2-full-mlx')


if __name__=='__main__':unittest.main()
