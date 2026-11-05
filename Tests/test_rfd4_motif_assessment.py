"""Motif correspondence, distinct shape/placement gates, and native partner inputs."""
import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];PIPE=REPO/'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0]=[str(PIPE/'scripts'),str(REPO/'Sources/iProteinStudio/Resources/rfd3'),str(REPO/'Tests')]
import gemmi
import numpy as np
from rfd4.contract import normalize,prediction_budget
from rfd4.motif_metrics import score,hit_verdict,insertion_map
from test_rfd4_motif import motif,Native,ROOT


def small_structure(path,shift=0):
    st=gemmi.Structure();model=gemmi.Model('1')
    points=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]
    for c in ['A','B']:
        chain=gemmi.Chain(c);res=gemmi.Residue();res.name='ALA';res.seqid=gemmi.SeqId(77,' ');res.subchain=c;res.het_flag='A'
        for name,xyz in zip(['N','CA','C','O'],points):
            atom=gemmi.Atom();atom.name=name;atom.element=gemmi.Element('O' if name=='O' else 'N' if name=='N' else 'C');atom.pos=gemmi.Position(xyz[0]+(shift if c=='A' else 10),xyz[1],xyz[2]);res.add_atom(atom)
        chain.add_residue(res);model.add_chain(chain)
    st.add_model(model);st.setup_entities();st.make_mmcif_document().write_file(str(path))
    mapped=[dict(chain='A',position=1,atom=n,component='ALA',xyz=p) for n,p in zip(['N','CA','C','O'],points)]
    context=dict(anchors=[dict(chain='B',position=1,atom=n,xyz=[p[0]+10,p[1],p[2]]) for n,p in zip(['N','CA','C','O'],points)])
    return mapped,context


def partner_fixture(folder):
    """T4 plus a displaced T4 fragment and lactate: wiring fixture, not a binding pose."""
    from test_rfd4_mixed_target import fixture
    ligand_path,cfg,_=fixture(folder)
    ligand=gemmi.read_structure(str(ligand_path))[0]['C'].clone()
    st=gemmi.read_structure(str(REPO/'Sources/iProteinStudio/Resources/examples/t4_lysozyme/2LZM.pdb'))
    # Preserve one protein chain only; omit crystallographic solvent.
    st.remove_waters();first=st[0]['A'].clone()
    model=gemmi.Model('1');model.add_chain(first)
    partner=gemmi.Chain('B')
    for res in list(first)[:12]:
        r=res.clone()
        for a in r:a.pos.x+=30;a.pos.y+=25
        partner.add_residue(r)
    model.add_chain(partner);model.add_chain(ligand)
    for chain in model:
        for residue in chain:residue.subchain=chain.name
    result=gemmi.Structure();result.add_model(model);result.setup_entities();result.assign_label_seq_id(force=True)
    path=folder/'partner-fixture.cif';result.make_mmcif_document().write_file(str(path))
    from rfd4.mixed_target import write_components
    write_components(path,cfg['target_ligands'])
    return path


class Contracts(unittest.TestCase):
    def request(self):return dict(task='motif',source='source.cif',motif=motif(),motif_assessment=dict(apo=True,holo=False,rmsd_max=2),predictor='esmfold2-fast-mlx')
    def test_budget_and_rejection(self):
        request=self.request();cfg=normalize(request);self.assertEqual(prediction_budget(cfg),1)
        for update in [dict(apo=False),dict(holo=True),dict(rmsd_max=float('nan')),dict(rmsd_max=-1),dict(placement_rmsd_max=1)]:
            r=copy.deepcopy(request);r['motif_assessment'].update(update)
            with self.assertRaises(ValueError):normalize(r)
        request['motif']['partner_chains']=['B'];request['motif_assessment']['holo']=True;request['count']=3
        self.assertEqual(prediction_budget(normalize(request)),6)
        request['motif']['partner_chains']=['A']
        with self.assertRaises(ValueError):normalize(request)
    def test_shape_and_placement_are_distinct(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'m.cif';mapped,context=small_structure(path,shift=5)
            measured=score(path,mapped,context,fix_sequence=True,holo=True)
            self.assertAlmostEqual(measured['motif_rmsd_angstrom'],0)
            self.assertAlmostEqual(measured['partner_aligned_motif_rmsd_angstrom'],5)
            policy=dict(apo=True,holo=True,rmsd_max=1,placement_rmsd_max=2)
            self.assertFalse(hit_verdict(dict(apo=measured,holo=measured),policy))
            with self.assertRaises(ValueError):hit_verdict(dict(apo=measured),policy)
            policy.update(placement_rmsd_max=None,rmsd_max=None)
            self.assertIsNone(hit_verdict(dict(apo=measured,holo=measured),policy))
            mapped[0]['atom']='CB'
            with self.assertRaises(ValueError):score(path,mapped,context,fix_sequence=True,holo=False)
    def test_missing_nonfinite_and_degenerate_never_pass(self):
        policy=dict(apo=False,holo=True,rmsd_max=2,placement_rmsd_max=2)
        self.assertTrue(hit_verdict({'holo':dict(motif_rmsd_angstrom=2,partner_aligned_motif_rmsd_angstrom=2)},policy))
        for bad in [None,float('nan'),float('inf')]:
            self.assertFalse(hit_verdict({'holo':dict(motif_rmsd_angstrom=0,partner_aligned_motif_rmsd_angstrom=bad)},policy))
    def test_geometry_bridge_from_predictor_environment(self):
        interpreter=ROOT/'venvs/NanoHunter_esmfold2/bin/python'
        if not interpreter.exists():self.skipTest('Pinned ESMFold2 environment is not installed')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'source.cif';mapped,context=small_structure(source,5)
            request=folder/'input.json';request.write_text(json.dumps(dict(mapped=mapped,context=context,fix_sequence=True,holo=True)))
            code="from rfd4.motif_geometry import operation; import json,sys; from pathlib import Path; value,_=operation(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),'score',**json.loads(Path(sys.argv[4]).read_text())); print(json.dumps(value))"
            p=subprocess.run([str(interpreter),'-B','-c',code,str(ROOT),str(folder/'metrics'),str(source),str(request)],env=dict(os.environ,PYTHONPATH=str(PIPE/'scripts')),capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            result=json.loads(p.stdout);self.assertAlmostEqual(result['motif_rmsd_angstrom'],0);self.assertAlmostEqual(result['partner_aligned_motif_rmsd_angstrom'],5)
    def test_protenix_apo_holo_does_not_reuse_the_wrong_msa_policy(self):
        from unittest.mock import patch
        from rfd4.motif_assessment import Predictor
        import yaml
        sessions=[]
        class Session:
            def __init__(self,cfg):self.cfg=cfg;self.closed=False;sessions.append(self)
            def predict(self,source,output,count):
                doc=yaml.safe_load(next(source.glob('*.yaml')).read_text())
                assert any(r['protein']['msa']!='empty' for r in doc['sequences'])==self.cfg['use_msa']
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'NANOHUNTER_ROOT':str(ROOT)}),patch('resident_predictor.make_session',Session),patch('rfd4.predictors.prediction_files',return_value=(Path('model.cif'),Path('confidence.json'))):
            root=Path(tmp);predictor=Predictor(dict(output=str(root),settings=dict(predictor='protenix-v2')))
            for mode,msa in [('apo','empty'),('holo','partner.a3m'),('holo-repeat','partner.a3m')]:
                folder=root/mode;folder.mkdir();yp=folder/'input.yaml';yp.write_text(yaml.safe_dump(dict(sequences=[dict(protein=dict(id='A',sequence='A',msa=msa))])))
                predictor.predict(yp,folder/'output')
            self.assertEqual(len(sessions),2);self.assertTrue(sessions[0].closed);self.assertFalse(sessions[1].closed)
            predictor.close();self.assertTrue(sessions[1].closed)
    def test_assessment_receipts_reuse_both_modes_and_reject_tampering(self):
        import yaml
        from unittest.mock import patch
        from rfd4.contract import sha
        from rfd4.motif_assessment import execute
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'NANOHUNTER_ROOT':str(ROOT)}):
            folder=Path(tmp);native=folder/'native.cif';mapped,context=small_structure(native,5)
            doc=gemmi.cif.read_file(str(native));block=doc.sole_block();table=block.get_mmcif_category('_atom_site.')
            table['annotation_src-coordinate-conditioned-region_1_atom']=['A1' if c=='A' else '.' for c in table['label_asym_id']]
            block.set_mmcif_category('_atom_site.',table);doc.write_file(str(native))
            reference=folder/'reference.json';reference.write_text(json.dumps(dict(atoms=[dict(origin='A1',source_residue='A:10',atom=a['atom'],component=a['component'],xyz=a['xyz']) for a in mapped])))
            parent=dict(id='seed_1',family='seed_1',structure=str(native),native_structure=str(native),structure_sha256=sha(native))
            (folder/'generated.json').write_text(json.dumps([parent]))
            config=dict(output=str(folder),motif_reference=str(reference),motif_context=context,target_sequences={'B':'A'},settings=dict(motif=dict(fix_sequence=True),motif_assessment=dict(apo=True,holo=True,rmsd_max=1,placement_rmsd_max=2),predictor='esmfold2-fast-mlx',target_msa='empty'))
            class FakePredictor:
                calls=0
                def predict(self,yp,output):
                    self.calls+=1;document=yaml.safe_load(yp.read_text());assert set(document)=={'version','sequences'}
                    chains=[r['protein']['id'] for r in document['sequences']];st=gemmi.read_structure(str(native))
                    if 'B' not in chains:del st[0]['B']
                    output.mkdir(parents=True);p=output/'model.cif';st.make_mmcif_document().write_file(str(p));confidence=output/'confidence.json';confidence.write_text('{"ptm":0.7}')
                    return p,confidence
            fake=FakePredictor();rows=execute(config,predictor=fake)
            self.assertEqual(fake.calls,2);self.assertEqual(len(rows),2);self.assertTrue(all(r['hit_filter_passed'] is False for r in rows))
            self.assertEqual(rows,execute(config,predictor=fake));self.assertEqual(fake.calls,2)
            Path(rows[0]['confidence']).write_text('{}')
            with self.assertRaises(ValueError):execute(config,predictor=fake)
            self.assertEqual(fake.calls,2)


class NativePartners(Native):
    # Reuse the existing real subprocess author/audit helper, not mocked features.
    def test_context_and_native_reference(self):
        source=partner_fixture(self.out)
        inspection=self.action('inspect-motif',dict(source=str(source)),self.out/'inspection')
        self.assertEqual(inspection.returncode,0,inspection.stderr)
        inventory=json.loads((self.out/'inspection/motif-inspection.json').read_text())
        self.assertEqual([c['chain'] for c in inventory['chains']],['A','B'])
        label=inventory['ligands'][0]['id']
        for name,partners,ligands in [('ppi',['B'],[]),('ligand',[],[label]),('mixed',['B'],[label])]:
            request=dict(task='motif',source=str(source),motif=dict(motif(),partner_chains=partners,ligand_ids=ligands),motif_assessment=dict(apo=True,holo=True,rmsd_max=2,placement_rmsd_max=2),predictor='esmfold2-fast-mlx')
            leaf=self.out/name
            for action in ['author','audit']:
                p=self.action(action,request,leaf);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            reference=json.loads((leaf/'motif_reference.json').read_text());self.assertEqual(len(reference['atoms']),12)
            context=json.loads((leaf/'motif_context.json').read_text());self.assertGreaterEqual(len(context['anchors']),6)
            spec=json.loads((leaf/'condition_spec.json').read_text());self.assertIn('/0',spec['contig'])


if __name__=='__main__':unittest.main()
