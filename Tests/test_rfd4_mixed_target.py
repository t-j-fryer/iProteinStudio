"""Molecular context contracts, without model inference or network access."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'),str(ROOT/'Sources/iProteinStudio/Resources/rfd3')]
import gemmi
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from biotite.interface.rdkit import from_mol
from rfd4.mixed_target import (molecule_record,write_components,native_names,canonical_assembly,
                              assembly_metrics,add_prediction_ligands,write_mpnn_parent,audit_conditioned)
from rfd4.contract import normalize


def fixture(folder):
    mol=Chem.AddHs(Chem.MolFromSmiles('C[C@@H](O)C(=O)[O-]'))
    AllChem.EmbedMolecule(mol,randomSeed=42)
    mol=Chem.RemoveHs(mol)
    atoms=from_mol(mol)[0]
    atoms=atoms[atoms.element!='H']
    atoms.atom_name=np.array(['C1','C2','O1','C3','O2','O3'])
    atoms.res_name[:]='L;0';atoms.chain_id[:]='C';atoms.res_id[:]=1
    ligand=molecule_record(atoms,'L:1:LAC','C','L;0')
    structure=gemmi.Structure();model=gemmi.Model('1');structure.add_model(model)
    model=structure[0]
    for name,seq in [('A',['SER','GLY']),('B',['ALA','GLY'])]:
        chain=gemmi.Chain(name)
        for i,aa in enumerate(seq,1):
            r=gemmi.Residue();r.name=aa;r.seqid=gemmi.SeqId(i,' ');r.het_flag='A'
            a=gemmi.Atom();a.name='CA';a.element=gemmi.Element('C');a.pos=gemmi.Position(20+i*4,20 if name=='A' else 30,0)
            r.add_atom(a);chain.add_residue(r)
        model.add_chain(chain)
    chain=gemmi.Chain('C');r=gemmi.Residue();r.name='L;0';r.seqid=gemmi.SeqId(1,' ');r.het_flag='H'
    for rec in ligand['atoms']:
        a=gemmi.Atom();a.name=rec['name'];a.element=gemmi.Element(rec['element']);a.charge=rec['charge'];a.pos=gemmi.Position(*rec['xyz']);r.add_atom(a)
    chain.add_residue(r);model.add_chain(chain);structure.setup_entities()
    path=folder/'input.cif';structure.make_mmcif_document().write_file(str(path))
    manifest=dict(schema=1,ligands=[ligand]);write_components(path,manifest)
    config=dict(settings=normalize(dict(task='protein',source=str(path),target_msa='empty')),target_sequences={'B':'AG'},target_ligands=manifest)
    return path,config,atoms


class MixedTargetTests(unittest.TestCase):
    def test_charge_stereo_and_input_identity_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,cfg,atoms=fixture(Path(tmp));ligand=cfg['target_ligands']['ligands'][0]
            self.assertEqual(ligand['formal_charge'],-1)
            self.assertIn('@',ligand['smiles'])
            self.assertEqual(audit_conditioned(atoms,cfg['target_ligands'])[0]['atoms'],6)
            document=add_prediction_ligands(dict(sequences=[{'protein':{'id':'A','sequence':'SG'}}]),cfg)
            self.assertEqual(document['sequences'][1]['ligand'],dict(id='C',smiles=ligand['smiles']))
            out=canonical_assembly(path,Path(tmp)/'normal.cif',cfg)
            report=assembly_metrics(out,cfg)
            self.assertTrue(report['passed'],report)
            self.assertTrue(report['ligands'][0]['stereochemistry_preserved'])
            write_mpnn_parent(out,Path(tmp)/'parent.pdb',cfg,{'A':'A','B':'B'})
            model=gemmi.read_structure(str(Path(tmp)/'parent.pdb'))[0]
            self.assertEqual(len(model['C'][0]),6)
            self.assertEqual({a.name for a in model['C'][0]},{a['name'] for a in ligand['atoms']})

    def test_predictor_atom_conventions_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path,cfg,_=fixture(folder);ligand=cfg['target_ligands']['ligands'][0]
            for predictor in ['boltz','intellifold','intellifold-full','protenix-v2','protenix-constraint-v0.5','esmfold2-full-mlx','esmfold2-fast-mlx','esmfold2-600-mlx','openfold-3-mlx']:
                st=gemmi.read_structure(str(path));atoms={a.name:a for a in st[0]['C'][0]}
                for name,rec in zip(native_names(ligand['smiles'],predictor),ligand['atoms']):atoms[rec['name']].name=name
                native=folder/(predictor+'.cif');st.make_mmcif_document().write_file(str(native))
                out=canonical_assembly(native,folder/(predictor+'-normal.cif'),cfg,predictor=predictor)
                self.assertTrue(assembly_metrics(out,cfg)['passed'],predictor)

    def test_missing_atoms_entities_and_nonfinite_coordinates_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path,cfg,_=fixture(folder)
            for mode in ['atom','ligand','extra','element','nan']:
                st=gemmi.read_structure(str(path))
                if mode=='atom':del st[0]['C'][0][0]
                elif mode=='ligand':del st[0]['C']
                elif mode=='extra':
                    extra=st[0]['C'].clone();extra.name='D';st[0].add_chain(extra)
                elif mode=='element':st[0]['C'][0][0].element=gemmi.Element('S')
                else:st[0]['C'][0][0].pos.x=float('nan')
                broken=folder/'bad.cif';st.make_mmcif_document().write_file(str(broken))
                with self.assertRaises(ValueError,msg=mode):canonical_assembly(broken,folder/'out.cif',cfg)

    def test_stereo_inversion_is_not_a_passing_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path,cfg,_=fixture(folder);st=gemmi.read_structure(str(path))
            for atom in st[0]['C'][0]:atom.pos.x=-atom.pos.x
            bad=folder/'mirror.cif';st.make_mmcif_document().write_file(str(bad))
            report=assembly_metrics(bad,cfg)
            self.assertFalse(report['passed']);self.assertFalse(report['ligands'][0]['stereochemistry_preserved'])

    def test_multiple_ligands_and_pose_diagnostics(self):
        import copy
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path,cfg,_=fixture(folder)
            cfg['target_ligands']['target_ca']={'B':[[24.,30.,0.],[28.,30.,0.]]}
            st=gemmi.read_structure(str(path));second=st[0]['C'].clone();second.name='D'
            for a in second[0]:a.pos.y+=10
            st[0].add_chain(second)
            ligand=copy.deepcopy(cfg['target_ligands']['ligands'][0]);ligand.update(chain='D',source_id='L:2:LAC')
            for a in ligand['atoms']:a['xyz'][1]+=10
            cfg['target_ligands']['ligands'].append(ligand)
            source=folder/'two.cif';st.make_mmcif_document().write_file(str(source))
            normalized=canonical_assembly(source,folder/'normalized.cif',cfg)
            report=assembly_metrics(normalized,cfg)
            self.assertTrue(report['passed'],report);self.assertEqual(len(report['ligands']),2)
            self.assertLess(max(r['target_aligned_ligand_rmsd_angstrom'] for r in report['ligands']),.001)
            for a in st[0]['D'][0]:a.pos.y-=10
            st.make_mmcif_document().write_file(str(source))
            self.assertFalse(assembly_metrics(source,cfg)['passed'])

    def test_component_tables_survive_repeated_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,cfg,_=fixture(Path(tmp));doc=gemmi.cif.read_file(str(path));block=doc.sole_block()
            existing=block.get_mmcif_category('_chem_comp.')
            existing['id'].append('ZZZ');existing['type'].append('L-peptide linking');existing['name'].append('Preserved custom component')
            block.set_mmcif_category('_chem_comp.',existing);doc.write_file(str(path))
            for _ in range(2):write_components(path,cfg['target_ligands'])
            ids=gemmi.cif.read_file(str(path)).sole_block().get_mmcif_category('_chem_comp.')['id']
            self.assertEqual(ids.count('ZZZ'),1);self.assertEqual(ids.count('L;0'),1)

if __name__=='__main__':unittest.main()
