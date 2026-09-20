import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts/nise/nesso_ccd_cache.py'
spec=importlib.util.spec_from_file_location('nesso_ccd_cache',SOURCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CCDCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ccd'
        self.path.write_bytes(b'verified CCD fixture')
    def tearDown(self):self.tmp.cleanup()
    def test_mutation_does_not_leak_between_requests(self):
        calls=[]
        def load(path):calls.append(path);return {'ALA':{'property':1},'UNK':None}
        cache=module.StandardAACache(self.path,load,dict)
        first=cache.get();first['ALA']['property']=19;first.pop('UNK')
        second=cache.get()
        self.assertEqual(second,{'ALA':{'property':1},'UNK':None})
        self.assertEqual(len(calls),1);self.assertEqual(cache.receipt()['requests'],2)
    def test_changed_file_is_rejected(self):
        cache=module.StandardAACache(self.path,lambda p:{'ALA':{}},dict)
        cache.get();self.path.write_bytes(b'changed fixture bytes')
        with self.assertRaisesRegex(RuntimeError,'CCD changed'):cache.get()
    def test_missing_file_is_rejected(self):
        cache=module.StandardAACache(self.path,lambda p:{},dict)
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):cache.get()
    def test_failed_load_is_not_cached(self):
        attempts=[]
        def load(path):
            attempts.append(1)
            if len(attempts)==1:raise ValueError('bad CCD')
            return {'ALA':{}}
        cache=module.StandardAACache(self.path,load,dict)
        with self.assertRaises(ValueError):cache.get()
        self.assertEqual(cache.get(),{'ALA':{}})
        self.assertEqual(cache.loads,1)
if __name__=='__main__':unittest.main()
