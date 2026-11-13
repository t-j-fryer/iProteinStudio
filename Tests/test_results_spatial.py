"""Synthetic CPU-only poses. No model weights, inference or private molecules."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts/results_spatial.py'
spec = importlib.util.spec_from_file_location('results_spatial', HELPER)
spatial = importlib.util.module_from_spec(spec); spec.loader.exec_module(spatial)

def policy(mode='protein', **updates):
    value = dict(schema=1, mode=mode, binderChains='A', targetChain='B' if mode=='protein' else 'L',
                 residues='10,11A', ligandResidue='901', atoms='C1,O1', cutoff='8', coverage='all',
                 requireGeometry=False, minimumBurial='', maximumBurial='')
    value.update(updates); return value

def pose(path, ligand=False, far=False):
    import gemmi
    st=gemmi.Structure(); model=gemmi.Model('1')
    def add(chain_id, residue_id, component, records):
        chain=next((c for c in model if c.name==chain_id), None)
        if chain is None: model.add_chain(gemmi.Chain(chain_id)); chain=model[-1]
        residue=gemmi.Residue(); residue.name=component; residue.seqid=gemmi.SeqId(int(residue_id[:-1]), residue_id[-1]) if residue_id[-1].isalpha() else gemmi.SeqId(residue_id)
        for name,el,xyz in records:
            atom=gemmi.Atom();atom.name=name;atom.element=gemmi.Element(el);atom.pos=gemmi.Position(*xyz);atom.occ=1
            residue.add_atom(atom)
        chain.add_residue(residue)
    add('A','1','ALA',[('CA','C',(0,0,0)),('H','H',(2.9,0,0))])
    if ligand:
        offset=30 if far else 0
        add('L','901','UNL',[('C1','C',(3+offset,0,0)),('O1','O',(7+offset,0,0))])
    else:
        add('B','10','ALA',[('CA','C',(3,0,0))]);add('B','11A','ALA',[('CA','C',(9,0,0))])
    st.add_model(model)
    if path.suffix=='.pdb':st.write_pdb(str(path))
    else:st.make_mmcif_document().write_file(str(path))

class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'pose.cif';pose(self.source)
    def tearDown(self):self.tmp.cleanup()
    def test_residue_distances_and_insertion_codes(self):
        row=spatial.assess(self.source,policy(),self.root)
        self.assertEqual(row['distances'],{'10':3.0,'11A':9.0});self.assertFalse(row['passed'])
        self.assertTrue(spatial.assess(self.source,policy(coverage='any'),self.root)['passed'])
        self.assertTrue(spatial.assess(self.source,policy(cutoff='9'),self.root)['passed'])
        with self.assertRaisesRegex(ValueError,'absent'):spatial.assess(self.source,policy(residues='11'),self.root)
        inventory=spatial.inventory(self.source);self.assertEqual(inventory['chains']['B']['protein_residues'],['10','11A'])
    def test_pdb_matches_cif(self):
        pdb=self.root/'copy.pdb';pose(pdb)
        self.assertEqual(spatial.assess(pdb,policy(),self.root)['distances'],spatial.assess(self.source,policy(),self.root)['distances'])
    def test_invalid_policy_and_ambiguous_coordinates(self):
        for update in [dict(cutoff='nan'),dict(cutoff='-1'),dict(targetChain='A'),dict(residues=''),dict(minimumBurial='10')]:
            with self.assertRaises(ValueError):spatial.assess(self.source,policy(**update),self.root)
        import gemmi
        st=gemmi.read_structure(str(self.source));second=st[0].clone();second.name="2";st.add_model(second);st.make_mmcif_document().write_file(str(self.source))
        with self.assertRaisesRegex(ValueError,'one coordinate'):spatial.assess(self.source,policy(),self.root)
        pose(self.source);st=gemmi.read_structure(str(self.source));st[0]['A'].add_residue(st[0]['A'][0].clone());st.make_mmcif_document().write_file(str(self.source))
        with self.assertRaisesRegex(ValueError,'Duplicate'):spatial.assess(self.source,policy(),self.root)
    def test_exact_ligand_atoms_and_sasa(self):
        pose(self.source,True)
        row=spatial.assess(self.source,policy('ligand',cutoff='5'),self.root)
        self.assertEqual(row['distances'],{'C1':3.0,'O1':7.0});self.assertFalse(row['passed'])
        self.assertGreater(row['sasa']['buried_percent'],0);self.assertLessEqual(row['sasa']['buried_percent'],100)
        self.assertGreater(row['sasa']['isolated_sasa_a2'],row['sasa']['complex_sasa_a2'])
        with self.assertRaisesRegex(ValueError,'absent'):spatial.assess(self.source,policy('ligand',atoms='O9'),self.root)
        pose(self.source,True,True)
        self.assertAlmostEqual(spatial.assess(self.source,policy('ligand'),self.root)['sasa']['buried_percent'],0,places=8)
    def request(self,p):
        return dict(policy=p,policy_sha256=spatial.digest(p),cache=str(self.root/'cache'),units=[dict(id='candidate',source_item_id='complex',source=str(self.source),source_stamp='fixture')])
    def run_review(self,p):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):spatial.run(self.request(p))
        return json.loads(stream.getvalue())
    def test_recorded_geometry_and_checkpoint_integrity(self):
        pose(self.source,True)
        p=policy('ligand',requireGeometry=True)
        self.assertFalse(self.run_review(p)['passed'])
        result=dict(passed=True,structure_sha256=spatial.sha(self.source));raw=json.dumps(result,sort_keys=True,allow_nan=False)
        side=Path(str(self.source)+'.ligand_geometry.json')
        side.write_text(json.dumps(dict(result=result,result_json=raw,result_sha256=hashlib.sha256(raw.encode()).hexdigest())))
        row=self.run_review(p);self.assertTrue(row['passed']);self.assertTrue(row['recorded_geometry']['passed'])
        self.assertEqual(row,self.run_review(p))
        receipt=Path(row['receipt']);saved=json.loads(receipt.read_text());saved['result']['passed']=False;receipt.write_text(json.dumps(saved))
        self.assertIn('integrity',self.run_review(p)['error'])
    def test_burial_range_filter_and_changed_pose(self):
        pose(self.source,True)
        p=policy('ligand',minimumBurial='100')
        first=self.run_review(p);self.assertFalse(first['passed'])
        pose(self.source,True,True)
        second=self.run_review(p);self.assertNotEqual(first['source_sha256'],second['source_sha256'])
        self.assertNotEqual(first['receipt'],second['receipt'])
    def test_optional_corrupt_geometry_and_concurrent_resume(self):
        pose(self.source,True)
        result=dict(passed=True,structure_sha256=spatial.sha(self.source))
        Path(str(self.source)+'.ligand_geometry.json').write_text(json.dumps(dict(result=result,result_sha256='invalid')))
        optional=self.run_review(policy('ligand'))
        self.assertTrue(optional['passed']);self.assertIn('unavailable',optional['geometry_warning'])
        required=self.run_review(policy('ligand',requireGeometry=True))
        self.assertFalse(required['passed']);self.assertIn('integrity',required['error'])
        request=self.root/'request.json';request.write_text(json.dumps(self.request(policy('ligand'))))
        commands=[subprocess.Popen([sys.executable,'-B',str(HELPER),'run',str(request)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        rows=[]
        for command in commands:
            stdout,stderr=command.communicate(timeout=30);self.assertEqual(command.returncode,0,stderr);rows.append(json.loads(stdout))
        self.assertEqual(rows[0],rows[1])
    def test_ligand_in_same_author_chain(self):
        import gemmi
        pose(self.source,True)
        st=gemmi.read_structure(str(self.source));st[0]['A'].add_residue(st[0]['L'][0].clone());del st[0]['L']
        pdb=self.root/'same-chain.pdb';st.write_pdb(str(pdb))
        row=spatial.assess(pdb,policy('ligand',targetChain='A'),self.root)
        self.assertEqual(row['distances'],{'C1':3.0,'O1':7.0})
        with self.assertRaises(ValueError):spatial.assess(pdb,policy('ligand',targetChain='A',ligandResidue=''),self.root)
    def test_changed_threshold_reuses_measurements(self):
        with patch.object(spatial,'assess',wraps=spatial.assess) as measured:
            first=self.run_review(policy(cutoff='8'))
            second=self.run_review(policy(cutoff='9'))
            self.assertFalse(first['passed']);self.assertTrue(second['passed'])
            self.assertEqual(measured.call_count,1)
            self.assertEqual(first['distances'],second['distances'])
            self.assertNotEqual(first['policy_sha256'],second['policy_sha256'])
    def test_policy_digest_mismatch(self):
        request=self.request(policy());request['policy_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'digest'):spatial.run(request)

if __name__=='__main__':unittest.main()
