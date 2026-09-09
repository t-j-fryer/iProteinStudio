import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import continue_campaign as recovery

class FailureGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit=recovery.source_recovery.configure()
        cls.result=cls.audit.audit('remaining','boltz_h0')
    def test_rejection_stays_failed_and_has_no_replacement(self):
        self.assertEqual(recovery.review(self.result,self.audit),[8])
        self.assertFalse(self.result['operational_passed'])
        self.assertEqual(sum(r['outcome']=='completed' for r in self.result['trajectories']),8)
    def test_failed_pilot_does_not_authorize_expansion(self):
        result=copy.deepcopy(self.result);result['phase']='pilot'
        with self.assertRaisesRegex(RuntimeError,'failed pilot'):
            recovery.review(result,self.audit)
    def test_unstarted_run_requires_separate_diagnosis(self):
        result=copy.deepcopy(self.result)
        next(r for r in result['trajectories'] if r['outcome']=='failed')['outcome']='not_started'
        with self.assertRaisesRegex(RuntimeError,'Unstarted'):
            recovery.review(result,self.audit)
    def test_non_geometry_failure_is_not_reclassified(self):
        spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
        module=SimpleNamespace(validate=lambda path:[])
        with patch.object(recovery.importlib.util,'spec_from_file_location',return_value=spec),patch.object(recovery.importlib.util,'module_from_spec',return_value=module):
            with self.assertRaisesRegex(RuntimeError,'not an independently reproduced'):
                recovery.review(self.result,self.audit)

if __name__=='__main__':unittest.main()
