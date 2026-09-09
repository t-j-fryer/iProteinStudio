import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('benchmark',HERE/'campaign.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SelectionTests(unittest.TestCase):
    def row(self,name,seq,score,cycle='1'):
        return dict(name=name,sequence=seq,score=str(score),pbind=str(score-.5),ligand_plddt='50',cycle=cycle)

    def test_missing_masked_initial_and_duplicates_cannot_enter(self):
        rows=[self.row('low','AAA',.5),self.row('mid','CCC',.9),self.row('high','DDD',1.5),
              self.row('duplicate','AAA',1.4),self.row('mask','XXX',1),self.row('init','EEE',1,'0')]
        rows.append(dict(self.row('missing','FFF',1),pbind=''))
        selected,n=module.select(rows,3)
        self.assertEqual(n,3)
        self.assertEqual([r['name'] for r in selected],['low','mid','high'])

    def test_score_disagreement_fails_before_selection(self):
        rows=[dict(self.row('wrong','AAA',1),score='1.5')]
        with self.assertRaisesRegex(ValueError,'disagrees'):
            module.select(rows,2)

    def test_too_small_cohort_fails(self):
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            module.select([self.row('one','AAA',1)],50)

    def test_artifact_digest_detects_content_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'artifact';path.write_bytes(b'original')
            before=module.digest(path);path.write_bytes(b'changed')
            self.assertNotEqual(before,module.digest(path))


if __name__=='__main__': unittest.main()
