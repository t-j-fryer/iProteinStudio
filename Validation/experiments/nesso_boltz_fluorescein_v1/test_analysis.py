"""Synthetic-only acceptance for the complete report path and tamper detection."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('analysis',Path(__file__).with_name('analyse.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


class AnalysisTests(unittest.TestCase):
    def fixture(self,out):
        selected=[];hashes={}
        for i in range(50):
            name=f'fixture{i}';seq='A'*(65+i)
            p=.1+.01*i;pl=50+i;score=p+pl/100
            selected.append(dict(name=name,sequence=seq,phase='nise',cycle='1',origin=f'L{i%16}',score=str(score),pbind=str(p),ligand_plddt=str(pl)))
            for engine in ('nesso','boltz'):
                result=dict(session=engine+'-fixture',wall_seconds=2 if engine=='nesso' else 8,combined=score)
                if engine=='nesso':
                    result.update(native=dict(esm_seconds=.2,inference_seconds=1),scores=dict(entropy_crop_pl=1-pl/100,entropy_pl=.9-i*.01,affinity_probability_binary=p,affinity_pred_value=float(i)))
                    if i==0: result['scores']['entropy_crop_pl']=0;result['combined']=None
                else:result.update(scores=dict(pbind=p,ligand_plddt=pl),affinity=dict(affinity_pred_value=float(i)))
                path=out/'full'/engine/name/'completed.json';save(path,dict(input=dict(sequence=seq),result=result,files={}))
                hashes[str(path.relative_to(out/'full'))]=m.digest(path)
        for engine in ('nesso','boltz'):
            save(out/'full'/engine/'warmups'/'fixture'/'warmup.json',dict(result=dict(engine=engine,session=engine+'-fixture',wall_seconds=10),process_startup_wall_seconds=3))
        save(out/'selection.json',selected);save(out/'manifest.json',dict(hardware='Synthetic fixture, not a measurement'))
        save(out/'full/audit.json',dict(status='passed',paired_candidates=50,completed_files=hashes,sessions=dict(boltz=['boltz-fixture'],nesso=['nesso-fixture'])))

    def test_report_math_invalid_entropy_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out)
            with contextlib.redirect_stdout(io.StringIO()):m.analyse(out)
            summary=m.read(out/'analysis/summary.json')
            self.assertEqual(summary['speed_ratio_boltz_over_nesso'],4)
            self.assertEqual(summary['ratio_bootstrap_95ci'],[4,4])
            self.assertEqual(summary['eligible_placements'],49)
            self.assertEqual(summary['top10_overlap'],10)
            self.assertAlmostEqual(summary['correlations'][2]['spearman'],1)
            self.assertTrue((out/'analysis/overview.svg').is_file())
            path=out/'full/boltz/fixture0/completed.json';path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Receipt changed'):m.analyse(out)


if __name__=='__main__':unittest.main()
