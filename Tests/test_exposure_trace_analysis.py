"""A recovering candidate must count as a false early rejection."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'Validation/experiments/biotin_single_particle_v1/analyse.py'
SPEC = importlib.util.spec_from_file_location('exposure_analysis', PATH)
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class ExposurePolicyTests(unittest.TestCase):
    def test_recovery_and_first_trigger_and_persistence(self):
        def row(name, passes, final):
            return dict(id=name,steps=[25,50,75,200],passes=passes,final_pass=final,
                        elapsed_seconds=[1,2,3,4],total_seconds=5)
        result=MODULE.exposure_policies([
            row('recovers',[False,True,True,True],True),
            row('persistent',[False,False,False,False],False),
            row('late',[True,True,False,False],False)])
        self.assertEqual(result['fixed_step'][0]['false_rejections'],['recovers'])
        self.assertEqual(result['fixed_step'][0]['final_failures_caught'],1)
        policy=next(r for r in result['persistence'] if r['start_step']==25 and r['consecutive_checks']==2)
        self.assertEqual(policy['false_rejections'],[])
        self.assertEqual(policy['caught_final_failures'],1)
        self.assertEqual(policy['decisions'][0]['step'],50)
        self.assertEqual(policy['hypothetical_remaining_step_fraction'],150/600)
        self.assertEqual(policy['gross_remaining_traced_time_fraction'],3/15)


if __name__=='__main__':unittest.main()
