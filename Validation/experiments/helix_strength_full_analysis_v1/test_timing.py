import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import campaign_timing as timing


class TimingTests(unittest.TestCase):
    def test_overlapping_resident_trajectories_count_elapsed_span_once(self):
        rows=[dict(run='run_1',start_ts=10,end_ts=110,duration_sec=100),
              dict(run='run_2',start_ts=20,end_ts=110,duration_sec=90)]
        self.assertEqual(timing.phase_span(rows),100)

    def test_gaps_within_the_recorded_phase_remain_elapsed_time(self):
        rows=[dict(run='run_1',start_ts=10,end_ts=20,duration_sec=10),
              dict(run='run_2',start_ts=30,end_ts=50,duration_sec=20)]
        self.assertEqual(timing.phase_span(rows),40)

    def test_invalid_duplicate_and_inconsistent_timers_fail(self):
        valid=dict(run='run_1',start_ts=10,end_ts=20,duration_sec=10)
        for rows in [[],[valid,valid],[{**valid,'duration_sec':9}],
                     [{**valid,'end_ts':float('nan')}],[{**valid,'end_ts':5}]]:
            with self.assertRaises(ValueError): timing.phase_span(rows)

    def test_combines_phases_weights_outputs_and_verifies_source_hashes(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); last=None
            for phase,count,duration in [('pilot',1,100),('remaining',9,900)]:
                hashes={}
                for i in range(count):
                    path=root/f'campaigns/{phase}__fixture_h0/run_{i:03d}/timing_run.csv'
                    path.parent.mkdir(parents=True)
                    with path.open('w',newline='') as stream:
                        writer=csv.DictWriter(stream,fieldnames=['run','start_ts','end_ts','duration_sec'])
                        writer.writeheader();writer.writerow(dict(run=f'run_{i:03d}',start_ts=10000,end_ts=10000+duration,duration_sec=duration))
                    hashes[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest();last=path
                audit=root/f'audits/{phase}/fixture_h0.json';audit.parent.mkdir(parents=True)
                audit.write_text(json.dumps(dict(raw_sha256=hashes,trajectories=[dict(outcome='completed',completed_cycles=5)]*count)))
            result=timing.summarize(root,['fixture'],['0'])['arms']['fixture_h0']
            self.assertEqual(result['optimized_designs'],50)
            self.assertEqual(result['recorded_span_seconds'],1000)
            self.assertEqual(result['seconds_per_design'],20)
            last.write_text(last.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'changed'):timing.summarize(root,['fixture'],['0'])


if __name__=='__main__':unittest.main()
