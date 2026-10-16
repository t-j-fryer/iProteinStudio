import json
from pathlib import Path
import tempfile
import unittest
from common import save,seal,verified
from prepare import select
from run import stage


class Contract(unittest.TestCase):
    def test_selection_is_stratified_unique_and_reproducible(self):
        rows=[dict(stage=p,pbind=i/40,unit=f'{p}/{i}',sequence=f'{p}-{i}')
              for p in ('phase0','optimization') for i in range(40)]
        selected=select(rows,7)
        self.assertEqual(selected,select(rows,7));self.assertEqual(len(selected),24)
        self.assertEqual(len({r['sequence'] for r in selected}),24)
        for stage_name in ('phase0','optimization'):
            for tier in range(3):
                self.assertEqual(sum(r['stage']==stage_name and r['score_tertile']==tier for r in selected),4)

    def test_insufficient_diversity_fails(self):
        with self.assertRaises(RuntimeError):select([dict(stage='phase0',pbind=.2,unit='x',sequence='A')],7)

    def test_resume_rejects_changed_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save(p/'result.json',dict(n=1));seal(p,dict(ok=True))
            self.assertEqual(verified(p),dict(ok=True));save(p/'result.json',dict(n=2))
            with self.assertRaises(RuntimeError):verified(p)

    def test_stage_preserves_cache_and_full_precision_input(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f=root/'frozen';(f/'processed/records').mkdir(parents=True);(f/'prediction').mkdir()
            (f/'x.yaml').write_text('version: 1\n')
            save(f/'processed/records/x.json',dict(id='x',affinity=True))
            save(f/'processed/manifest.json',dict(records=[]))
            (f/'prediction/pre_affinity_x.npz').write_bytes(b'full precision source')
            source=stage(root/'run',[dict(directory=str(f),name='x')])
            self.assertEqual(source.name,'yaml')
            result=root/'run/prediction/boltz_results_yaml'
            self.assertFalse((result/'processed/manifest.json').exists())
            self.assertTrue(json.loads((result/'processed/records/x.json').read_text())['affinity'])
            self.assertEqual((result/'predictions/x/pre_affinity_x.npz').read_bytes(),b'full precision source')


if __name__=='__main__':unittest.main()
