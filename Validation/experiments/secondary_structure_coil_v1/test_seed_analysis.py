"""Meaningful endpoint, pairing and durable-monitor behavior checks."""
import copy
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import summarize_seed as summary


class SummaryTests(unittest.TestCase):
    def rows(self):
        rows=[]
        # Cell values produce interaction .4-.2-.15+.1=.15. Varying the
        # final cycle checks that primary means do not silently select it.
        values={summary.REFERENCE:.1,summary.ARMS[0]:.2,summary.ARMS[1]:.15,summary.ARMS[2]:.4}
        for arm,value in values.items():
            for i in range(1,11):
                for cycle in range(6):
                    row=dict(arm=arm,run=f'run_{i:03d}',cycle=cycle)
                    row.update({k:value+(1 if cycle==0 else .05 if cycle==5 else 0) for k in summary.METRICS})
                    rows.append(row)
        return rows

    def test_interaction_and_cycle_exclusion(self):
        # Reduce computational repetitions only for this deterministic fixture;
        # production still uses the shared prospectively recorded 20,000.
        bootstrap=summary.prior.paired_bootstrap
        with patch.object(summary.prior,'paired_bootstrap',side_effect=lambda x:bootstrap(x,replicates=100)):
            result=summary.build_summary(self.rows())
        primary=result['optimized_cycles01_05']
        self.assertAlmostEqual(primary['arms'][summary.REFERENCE]['mean']['sheet_fraction'],.11)
        self.assertAlmostEqual(result['cycle05']['arms'][summary.REFERENCE]['mean']['sheet_fraction'],.15)
        self.assertAlmostEqual(result['cycle00']['arms'][summary.REFERENCE]['mean']['sheet_fraction'],1.1)
        self.assertAlmostEqual(primary['factorial_interaction']['sheet_fraction']['mean_difference'],.15)
        self.assertAlmostEqual(primary['paired_minus_reference'][summary.ARMS[0]]['sheet_fraction']['mean_difference'],.1)

    def test_missing_cycle_fails_instead_of_selecting_available(self):
        rows=self.rows();rows.pop()
        with self.assertRaisesRegex(ValueError,'missing required cycles'):
            summary.build_summary(rows)

    def test_only_declared_flags_are_removed_for_pairing(self):
        first=['--predictor','boltz','--turn-strength','.5','--ligand-temp-other','.1','--out-root','one']
        second=['--predictor','boltz','--turn-strength','.1','--ligand-temp-other','.1','--out-root','two']
        self.assertEqual(summary.comparable_arguments(first),summary.comparable_arguments(second))
        second[5]='.3'
        self.assertNotEqual(summary.comparable_arguments(first),summary.comparable_arguments(second))

    def test_fingerprint_mismatch_fails_before_analysis(self):
        first={'manifest':{'runtime':{'runner_sha256':'one'}},'report':{},'input_sha256':{'manifest':'m','audit':'a'}}
        second={'manifest':{'runtime':{'runner_sha256':'two'},'config':{'reference_control':{'arm':summary.REFERENCE,'manifest_sha256':'m','audit_sha256':'a'}}},'report':{}}
        with self.assertRaisesRegex(ValueError,'runtime differs'):
            summary.validate_pairing(first,second)


class MonitorTests(unittest.TestCase):
    def test_failed_job_never_audits_or_summarizes(self):
        monitor=importlib.import_module('monitor_seed')
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(monitor.base,'OUTPUT',Path(temporary)),patch.object(monitor.base,'CONFIG',{'arms':{'a':{}}}),patch.object(monitor.base,'status',return_value={'a':{'status':'failed'}}),patch.object(monitor.subprocess,'run') as process:
                self.assertEqual(monitor.worker(),1)
                process.assert_not_called()

    def test_missing_submitted_arm_fails_closed(self):
        monitor=importlib.import_module('monitor_seed')
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(monitor.base,'OUTPUT',Path(temporary)),patch.object(monitor.base,'CONFIG',{'arms':{'a':{},'b':{}}}),patch.object(monitor.base,'status',return_value={'a':{'status':'completed'}}),patch.object(monitor.subprocess,'run') as process:
                with self.assertRaisesRegex(RuntimeError,'arm set'):
                    monitor.worker()
                process.assert_not_called()


if __name__=='__main__':
    unittest.main()
