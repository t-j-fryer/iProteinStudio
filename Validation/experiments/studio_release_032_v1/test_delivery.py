import json,tempfile,unittest
from pathlib import Path
import finish_release as gate
class Tests(unittest.TestCase):
 def test_partial_duplicate_and_failed_cohorts_hold_publication(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);ledger=root/'jobs.json';ledger.write_text('[{"name":')
   manifest=dict(ledgers=[str(ledger)],expected_names=['a','b'])
   self.assertEqual(gate.cohort(manifest),[])
   jobs=[dict(name='a',job_id='job-a'),dict(name='b',job_id='job-b')]
   ledger.write_text(json.dumps(jobs));self.assertEqual(gate.cohort(manifest),jobs)
   for job in jobs:
    path=root/'jobs'/job['job_id']/'state.json';path.parent.mkdir(parents=True);path.write_text('{"status":"completed"}')
   self.assertTrue(gate.prior.ready(jobs,root,count=2));self.assertFalse(gate.prior.ready(jobs[:1],root,count=2))
   (root/'jobs/job-a/state.json').write_text('{"status":"failed"}')
   with self.assertRaises(RuntimeError):gate.prior.ready(jobs,root,count=2)
   ledger.write_text(json.dumps(jobs+[jobs[0]]))
   with self.assertRaises(ValueError):gate.cohort(manifest)
if __name__=='__main__':unittest.main()
