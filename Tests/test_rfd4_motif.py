"""Execute pinned native authoring/preparation, not merely syntax or mock checks."""
import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];PIPE=REPO/'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0,str(PIPE/'scripts'))
from rfd4.contract import normalize
ROOT=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio'))
SOURCE=REPO/'Sources/iProteinStudio/Resources/examples/t4_lysozyme/2LZM.pdb'
def motif():
 return dict(residues=[dict(chain='A',residue=i,atoms=['N','CA','C','O']) for i in [10,11,20]],coordinate_mode='absolute',fix_sequence=True,unindexed=False,group_segments=True,prefix=[8,8],linker=[5,5],suffix=[8,8])
class Contracts(unittest.TestCase):
 def test_defaults_explicit_optout_and_old_conditions(self):
  self.assertTrue(normalize({})['optimized_kernels'])
  self.assertFalse(normalize(dict(optimized_kernels=False))['optimized_kernels'])
  self.assertIsNone(normalize({})['motif'])
 def test_invalid_and_ambiguous_inputs(self):
  good=dict(task='motif',source=str(SOURCE),motif=motif());self.assertEqual(normalize(good)['motif'],good['motif'])
  for change in [dict(prefix=[0,10]),dict(fix_sequence=False,residues=[dict(chain='A',residue=10,atoms=['CB'])]),dict(residues=[]),dict(residues=motif()['residues']*2)]:
   bad=copy.deepcopy(good);bad['motif'].update(change)
   with self.assertRaises(ValueError):normalize(bad)
  for change in [dict(contig='A1-10'),dict(annotated_input=True),dict(task='protein'),dict(conditions=[dict(condition='C_CRD',value=True,selection="sel('A')")])]:
   with self.assertRaises(ValueError):normalize(dict(good,**change))
class Native(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def action(self,action,request,folder):
  folder.mkdir(exist_ok=True);cfg=folder/'settings.json';cfg.write_text(json.dumps(request))
  p=subprocess.run([sys.executable,'-B',str(PIPE/'scripts/rfd4_cli.py'),action,'--root',str(ROOT),'--config',str(cfg),'--output',str(folder)],capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4'))
  (folder/(action+'.log')).write_text(p.stdout+p.stderr);return p
 def test_native_inventory_and_preview_ids(self):
  run=self.action('inspect-motif',dict(source=str(SOURCE)),self.out);self.assertEqual(run.returncode,0,run.stdout+run.stderr)
  data=json.loads((self.out/'motif-inspection.json').read_text());self.assertEqual(len(data['residues']),164)
  import gemmi
  structure=gemmi.read_structure(data['preview']);self.assertEqual({(c.name,r.seqid.num) for c in structure[0] for r in c},{(r['chain'],r['residue']) for r in data['residues']})
 def test_real_native_conditioning(self):
  for name,changes in [('absolute',{}),('relative',dict(coordinate_mode='relative')),('unindexed',dict(unindexed=True)),('variable',dict(prefix=[6,9],linker=[4,7])),('backbone_redesign',dict(fix_sequence=False))]:
   with self.subTest(name=name):
    request=dict(task='motif',source=str(SOURCE),motif=dict(motif(),**changes));folder=self.out/name
    for action in ['author','audit']:
     p=self.action(action,request,folder);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    spec=json.loads((folder/'condition_spec.json').read_text());self.assertTrue(json.loads((folder/'feature_audit.json').read_text())['passed'])
    self.assertIn('A10-11',spec['contig']);self.assertIn('A20-20',spec['contig'])
    self.assertEqual(len(spec['conditions']['C_CRDGRP' if name=='relative' else 'C_CRD'][str(1) if name=='relative' else 'true']),3)
    if name=='unindexed':self.assertEqual({r['group'] for r in spec['conditions']['C_IDX']['false']},{'segment_1','segment_2'})
 def test_missing_atom_rejected_by_native_authoring(self):
  m=motif();m['residues'][0]['atoms']=['NOTANATOM'];p=self.action('author',dict(task='motif',source=str(SOURCE),motif=m),self.out)
  self.assertNotEqual(p.returncode,0);self.assertIn('absent, ambiguous or lacks coordinates',p.stderr)
 def test_changed_inspected_source_rejected(self):
  m=motif();m['source_sha256']='0'*64
  p=self.action('author',dict(task='motif',source=str(SOURCE),motif=m),self.out)
  self.assertNotEqual(p.returncode,0);self.assertIn('source changed since inspection',p.stderr)
if __name__=='__main__':unittest.main()
