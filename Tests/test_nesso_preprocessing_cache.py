import importlib.util,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts/nise/nesso_preprocessing_cache.py'
spec=importlib.util.spec_from_file_location('nesso_preprocessing_cache',SOURCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Dumpable:
    def __init__(self,identity='input'):self.id=identity
    def dump(self,path):path.write_text('upstream bytes')

class PreprocessingCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.calls=[];self.parses=[]
        self.aa=types.SimpleNamespace(path=self.root/'ccd',get=lambda:{'ALA':object()})
        def preprocess(paths,**kw):
            self.calls.append(paths[0]);smiles=json.loads(paths[0].read_text())['sequences'][1]['ligand']['smiles']
            (kw['mol_dir']/(paths[0].stem+'__B.pkl')).write_bytes(('original conformer '+smiles).encode())
            return types.SimpleNamespace(records=[Dumpable(paths[0].stem)]),[]
        def parse(schema,mol_dir,ccd_dict,record_id):
            self.parses.append(schema)
            return Dumpable(),Dumpable(record_id),{},{}
        modules={'yaml':types.SimpleNamespace(safe_load=json.loads),
                 'nesso.main':types.SimpleNamespace(preprocess_yamls=preprocess),
                 'nesso.data.yaml_input':types.SimpleNamespace(parse_schema=parse),
                 'nesso.data.types':types.SimpleNamespace(Manifest=lambda records:types.SimpleNamespace(records=records))}
        self.patch=patch.dict(sys.modules,modules);self.patch.start()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def request(self,cache,index,smiles='CCO',sequence='AAA'):
        folder=self.root/str(index);folder.mkdir();q=folder/'input.yaml'
        schema={'sequences':[{'protein':{'id':'A','sequence':sequence}},{'ligand':{'id':'B','smiles':smiles}}]}
        q.write_text(json.dumps(schema));processed=folder/'processed';mols=processed/'rdkit_conformers';mols.mkdir(parents=True)
        cache.run(q,mols,processed)
        return folder,q
    def test_hit_uses_original_conformer_and_current_protein(self):
        cache=module.PreprocessingCache(self.aa)
        self.request(cache,0);folder,q=self.request(cache,1,sequence='CCC')
        self.assertEqual(len(self.calls),1)
        self.assertEqual((folder/'processed/cached_ligand.pkl').read_bytes(),b'original conformer CCO')
        self.assertEqual(self.parses[0]['sequences'][0]['protein']['sequence'],'CCC')
        self.assertNotIn('conformer',json.loads(q.read_text())['sequences'][1]['ligand'])
        self.assertEqual(cache.receipt()['hits'],1)
    def test_bounded_eviction_and_exact_smiles_keys(self):
        cache=module.PreprocessingCache(self.aa,capacity=1)
        for i,s in enumerate(['CCO','OCC','CCO']):self.request(cache,i,smiles=s)
        self.assertEqual(len(self.calls),3);self.assertEqual(len(cache.conformers),1)
    def test_noncanonical_protein_keeps_upstream_path(self):
        cache=module.PreprocessingCache(self.aa)
        self.request(cache,0);self.request(cache,1,sequence='AXA')
        self.assertEqual(len(self.calls),2);self.assertEqual(len(self.parses),0)
    def test_fresh_instance_has_no_cross_session_state(self):
        self.request(module.PreprocessingCache(self.aa),0)
        self.request(module.PreprocessingCache(self.aa),1)
        self.assertEqual(len(self.calls),2)
if __name__=='__main__':unittest.main()
