"""Contract checks for timed workflows, ligand selection and restart integrity."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/scripts'))
from rfd4 import budget
from rfd4.contract import atomic, normalize, seal, sha, verify
from rfd4.search import execute
from test_rfd4 import FakeEngine


class WorkflowTests(unittest.TestCase):
    def test_ligand_search_uses_combined_score_and_keeps_ancestry(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);parent=root/'parent.pdb';parent.write_text('test coordinates')
            cfg=normalize(dict(task='ligand',ligand_smiles='CCO',search='beam',predictor='boltz',
                               sequence_model='lasermpnn',cycles=2,proposals=2,beam_width=2))
            rows=execute(dict(settings=cfg),[dict(family='seed_42',id='seed_42',seed=42,
                structure=str(parent),structure_sha256=sha(parent))],FakeEngine(),root)
            self.assertEqual(len(rows),6)
            decision=json.loads((root/'decisions/seed_42/cycle_001.json').read_text())
            self.assertIn('ligand',decision['metric'])
            self.assertTrue(all(row['parent_id'] for row in rows))

    def test_invalid_and_explicit_input_contracts(self):
        for minutes in [0,-1,float('nan'),float('inf'),True,10081]:
            with self.subTest(minutes=minutes),self.assertRaises(ValueError):normalize(dict(time_budget_minutes=minutes))
        self.assertEqual(normalize(dict(task='ligand',ligand_smiles='CCO'))['source'],'')
        for changes in [dict(predictor='esmfold2-full-mlx'),dict(sequence_model='solublempnn'),dict(omit_amino_acids='')]:
            with self.assertRaises(ValueError):normalize(dict(task='ligand',ligand_smiles='CCO',search='beam',predictor='boltz',sequence_model='lasermpnn',**{})|changes)

    def test_budget_stops_at_boundary_and_preserves_unindexed_generation(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);now=[100.0]
            config=dict(output=str(root),settings=normalize(dict(count=3,time_budget_minutes=1)))
            atomic(root/'config.json',config);atomic(root/'studio_job.json',{'id':'fixture'})
            calls=[]
            def stage(action,path,child):
                calls.append(child)
                output=child/'generation/unit';output.mkdir(parents=True)
                model=output/'model.cif';model.write_text('durable output')
                seal(output/'completed.json',dict(id='unit',structure=str(model)),[model])
                now[0]+=61
                budget.checkpoint()
            with patch.object(budget.time,'monotonic',side_effect=lambda:now[0]):budget.run(root/'config.json',stage)
            self.assertEqual(len(calls),1)
            report=verify(root/'completed.json')
            self.assertEqual(report['saved_candidates'],1)
            self.assertTrue(report['partial_family'])
            self.assertEqual(report['reason'],'time_budget')
            self.assertNotIn('STUDIO_RFD4_DEADLINE',os.environ)

    def test_resume_counts_only_active_time_and_propagates_errors(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);now=[100.0]
            cfg=dict(output=str(root),settings=normalize(dict(count=2,time_budget_minutes=1)))
            atomic(root/'config.json',cfg);atomic(root/'studio_job.json',{'id':'fixture'})
            def fail(*args):now[0]+=5;raise RuntimeError('interrupted')
            with patch.object(budget.time,'monotonic',side_effect=lambda:now[0]),self.assertRaisesRegex(RuntimeError,'interrupted'):
                budget.run(root/'config.json',fail)
            self.assertFalse((root/'completed.json').exists())
            now[0]+=10000
            def complete(action,path,child):
                now[0]+=2;seal(child/'completed.json',dict(done=True),[path])
            with patch.object(budget.time,'monotonic',side_effect=lambda:now[0]):budget.run(root/'config.json',complete)
            self.assertEqual(json.loads((root/'active_time.json').read_text())['active_seconds'],9)
            self.assertEqual(verify(root/'completed.json')['complete_families'],2)


if __name__=='__main__':unittest.main()
