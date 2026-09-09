"""Executed lifecycle tests use opaque synthetic artifacts, no protein sequences."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from attempt_journal import Journal


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_resume_preserves_original_and_progression_decision(self):
        journal=Journal(self.root,2)
        journal.record(b'original opaque artifact',{'eligible':False,'reason':'synthetic flag'})
        resumed=Journal(self.root,2)
        result=resumed.record(b'second opaque artifact',{'eligible':True,'reason':'synthetic pass'})
        self.assertEqual(result['state'],'eligible')
        self.assertEqual(result['selected_attempt'],1)
        self.assertFalse(result['executes_next_stage'])
        self.assertEqual((self.root/'attempt_000000/artifact.bin').read_bytes(),b'original opaque artifact')

    def test_exhaustion_does_not_become_a_pass(self):
        journal=Journal(self.root,1)
        result=journal.record(b'opaque',{'eligible':False,'reason':'synthetic failure'})
        self.assertEqual(result['state'],'budget_exhausted')
        self.assertFalse(result['eligible_for_next_stage'])
        self.assertIsNone(result['selected_attempt'])
        with self.assertRaises(ValueError):journal.record(b'other',{'eligible':True,'reason':'pass'})

    def test_no_more_attempts_after_eligibility(self):
        journal=Journal(self.root,3)
        journal.record(b'opaque',{'eligible':True,'reason':'pass'})
        with self.assertRaises(ValueError):journal.record(b'other',{'eligible':False,'reason':'fail'})

    def test_resume_rejects_changed_budget(self):
        Journal(self.root,2)
        with self.assertRaises(ValueError):Journal(self.root,3)

    def test_corrupted_preserved_artifact_fails(self):
        journal=Journal(self.root,2)
        journal.record(b'original',{'eligible':False,'reason':'flag'})
        (self.root/'attempt_000000/artifact.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):journal.status()

    def test_interrupted_publication_is_not_a_completed_attempt(self):
        journal=Journal(self.root,2)
        with patch('attempt_journal.os.replace',side_effect=OSError('simulated interruption')):
            with self.assertRaises(OSError):journal.record(b'opaque',{'eligible':False,'reason':'flag'})
        self.assertEqual(journal.status()['recorded_attempts'],0)
        self.assertEqual(list(self.root.glob('.staging-*')),[])

    def test_invalid_assessment_cannot_enter_journal(self):
        journal=Journal(self.root,2)
        for value in ({'eligible':'yes','reason':'x'},{'eligible':True,'reason':''},
                      {'eligible':True,'reason':'x','score':float('nan')}):
            with self.assertRaises(ValueError):journal.record(b'opaque',value)
        self.assertEqual(journal.status()['recorded_attempts'],0)

    def test_gap_in_history_is_not_silently_skipped(self):
        journal=Journal(self.root,2)
        journal.record(b'opaque',{'eligible':False,'reason':'flag'})
        (self.root/'attempt_000000').rename(self.root/'attempt_000001')
        with self.assertRaises(ValueError):journal.status()


if __name__=='__main__':unittest.main()
