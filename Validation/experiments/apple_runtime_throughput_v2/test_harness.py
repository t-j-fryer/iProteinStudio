import json,tempfile,unittest
from pathlib import Path
from worker import atomic,sha
from coordinator import verify_complete,verify_seal
class Receipts(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def fixture(self):
  req=self.root/'request.json';atomic(req,{'seed':42});out=self.root/'out';out.mkdir();(out/'result').write_text('valid')
  atomic(out/'completed.json',dict(request_sha256=sha(req),files={'result':sha(out/'result')}));return req,out
 def test_intact(self):r,o=self.fixture();verify_complete(o,r)
 def test_output_mutation(self):
  r,o=self.fixture();(o/'result').write_text('changed')
  with self.assertRaises(RuntimeError):verify_complete(o,r)
 def test_extra_output(self):
  r,o=self.fixture();(o/'extra').write_text('new')
  with self.assertRaises(RuntimeError):verify_complete(o,r)
 def test_changed_request(self):
  r,o=self.fixture();atomic(r,{'seed':43})
  with self.assertRaises(RuntimeError):verify_complete(o,r)
 def test_missing_output(self):
  r,o=self.fixture();(o/'result').unlink()
  with self.assertRaises(RuntimeError):verify_complete(o,r)
 def test_source_mutation(self):
  source=self.root/'source';source.mkdir();(source/'code.py').write_text('old');seal=self.root/'seal.json';atomic(seal,dict(root=str(source),files={'code.py':sha(source/'code.py')}));verify_seal(seal);(source/'code.py').write_text('new')
  with self.assertRaises(RuntimeError):verify_seal(seal)
if __name__=='__main__':unittest.main()
