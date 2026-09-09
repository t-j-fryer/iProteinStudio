import unittest
import numpy as np
import analyse as a


class StatisticalUnitTests(unittest.TestCase):
    def test_constant_paired_difference_has_exact_interval(self):
        left=np.arange(10,dtype=float)
        self.assertEqual(a.ci((left+7)-left),[7.,7.,7.])

    def test_repeated_cycles_cannot_be_used_as_independent_replicates(self):
        with self.assertRaisesRegex(RuntimeError,'ten trajectories'):
            a.bounds(np.zeros(50))

    def test_paired_contrasts_reproduce_the_completed_campaign_report(self):
        current=a.read(a.OUT/'paired_contrasts.json')
        original=a.read(a.STUDY/'analysis/complete_review/paired_contrasts.json')['contrasts']
        for key,metrics in current.items():
            engine,contrast=key.split(':')
            lower,upper=contrast.split('->')
            original_key=f'{engine}: {lower.replace("p", ".")} to {upper.replace("p", ".")}'
            for metric,value in metrics.items():
                expected=original[original_key][metric]
                self.assertAlmostEqual(value['mean_difference'],expected['mean_difference'],places=10)
                np.testing.assert_allclose(value['bootstrap_95_ci'],expected['bootstrap_95_ci'],atol=1e-10,rtol=0)


if __name__=='__main__':unittest.main()
