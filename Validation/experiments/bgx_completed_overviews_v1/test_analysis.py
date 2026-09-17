import unittest
from analyse import trajectory_means, pooled_seconds, phase_span, ci

class AnalysisTests(unittest.TestCase):
    def test_trajectory_unit_not_individual_cycles(self):
        rows=[]
        for run,base in [(1,10),(2,20)]:
            for cycle in range(1,6):
                rows.append(dict(campaign='a',kind='minibinder',engine='boltz',condition='0',run=run,length=80,cycle=cycle,plddt=base+cycle,iptm=.5,helix=.3,sheet=.2,coil=.5))
        result=trajectory_means(rows)
        self.assertEqual(len(result),2)
        self.assertEqual([r['mean_plddt'] for r in result],[13,23])
        with self.assertRaises(ValueError):trajectory_means(rows+[rows[0]])
        with self.assertRaises(ValueError):trajectory_means(rows[:-1])

    def test_pool_weights_outputs_and_excludes_intercampaign_waits(self):
        # Seven versus six trajectories: arithmetic mean of scaffold costs is wrong.
        self.assertAlmostEqual(pooled_seconds([
            dict(recorded_span_seconds=350,optimized_designs=35),
            dict(recorded_span_seconds=600,optimized_designs=30)]),950/65)

    def test_overlapping_timers_count_once(self):
        self.assertEqual(phase_span([
            dict(run='a',start_ts=0,end_ts=100,duration_sec=100),
            dict(run='b',start_ts=20,end_ts=110,duration_sec=90)]),110)

    def test_bootstrap_supports_small_and_large_groups(self):
        for n in (6,7,50):
            self.assertEqual(ci([.75]*n),(.75,.75,.75))
            m,low,high=ci(list(range(n)))
            self.assertLessEqual(low,m);self.assertGreaterEqual(high,m)

if __name__=='__main__':unittest.main()
