import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import finish as f

class ReportTest(unittest.TestCase):
    def test_complete_matrix_and_constant_paired_differences(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'analysis').mkdir()
            (root/'manifest.json').write_text('{}')
            (root/'analysis/report.json').write_text('{"complete":true}')
            def records(phase,name):
                strength=f.c.CONFIG['arms'][name]['strength']
                ids=[1] if phase=='pilot' else range(2,11)
                return {'trajectories':[dict(arm=name,phase=phase,trajectory=i,outcome='completed',completed_cycles=5,
                    mean_helix=.6-.2*strength,mean_sheet=.1+.1*strength,mean_coil=.3+.1*strength,mean_plddt=80-10*strength) for i in ids]}
            with patch.object(f.c,'OUTPUT',root),patch.object(f.audit,'audit',side_effect=records):
                result=f.finish()
            self.assertTrue(result['complete'])
            contrasts=json.loads((root/'analysis/complete_review/paired_contrasts.json').read_text())['contrasts']
            self.assertEqual(len(contrasts),21)
            self.assertEqual(contrasts['boltz: 0.5 to 1']['plddt']['bootstrap_95_ci'],[-5.,-5.])
            self.assertEqual(contrasts['boltz: 0 to 1']['plddt']['n_pairs'],10)
            for filename in ['REPORT.md','all_engines.svg','all_engines.png']:
                self.assertGreater((root/'analysis/complete_review'/filename).stat().st_size,0)
if __name__=='__main__':unittest.main()
