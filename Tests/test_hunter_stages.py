"""CPU contract tests for the two-stage Hunter boundary (no model substitutes)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import hunter_stages as stages
import hunter_initialization_io as io


def pdb(path, chains=('A', 'B')):
    rows = []
    for chain in chains:
        for residue in range(1, 4):
            for atom, dx, element in [('N', 0, 'N'), ('CA', 1.4, 'C'), ('C', 2.6, 'C'), ('O', 3, 'O')]:
                rows.append(f'ATOM  {len(rows)+1:5d} {atom:^4s} ALA {chain}{residue:4d}    {residue*3.8+dx:8.3f}{float(chain=="B")*10:8.3f}{0.:8.3f}  1.00 50.00          {element:>2s}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(rows)+'\nEND\n')


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.template = self.root/'template.yaml'
        self.template.write_text('version: 1\nsequences:\n- protein:\n    id: A\n    sequence: XXX\n    msa: empty\n- protein:\n    id: B\n    sequence: AAA\n    msa: target.a3m\nconstraints:\n- pocket:\n    binder: A\n    contacts: [[B, 2]]\nnanohunter:\n  target_epitope_residues: [B2]\n')
        self.spec = dict(method='rfd3', initial_engine='rfd3', refinement_engine='esmfold2-fast-mlx', trajectories=1,
                         arguments=['--template-yaml',str(self.template)])
        self.source = self.root/'rfd3';self.output = self.root/'output'
        self.output.mkdir()
        pdb(self.source/'rfd3/backbones/design_0001.pdb')
    def tearDown(self): self.tmp.cleanup()
    def test_handoff_is_audited_and_tamper_detected(self):
        io.handoff(self.spec,self.source,self.output)
        receipt=stages.verify_handoff(self.output)
        self.assertFalse(receipt['cycle00_is_design'])
        target=self.output/'run_001/cycle_00/pred_min/model_0.pdb'
        target.write_text(target.read_text()+'REMARK changed\n')
        with self.assertRaisesRegex(ValueError,'changed'):stages.verify_handoff(self.output)
    def test_incomplete_cohort_cannot_commit(self):
        self.spec['trajectories']=2
        with self.assertRaisesRegex(ValueError,'Expected 2'):io.handoff(self.spec,self.source,self.output)
        self.assertFalse((self.output/'initialization.json').exists())
    def test_wrong_target_sequence_length_cannot_commit(self):
        self.template.write_text(self.template.read_text().replace('sequence: AAA','sequence: AAAA'))
        with self.assertRaisesRegex(ValueError,'do not match'):io.handoff(self.spec,self.source,self.output)
        self.assertFalse((self.output/'initialization.json').exists())
    def test_refinement_scope_and_original_immutable(self):
        original=self.template.read_bytes()
        output=self.root/'refinement.yaml'
        io.refinement_template(self.spec,output)
        data=io.yaml.safe_load(output.read_text())
        self.assertNotIn('constraints',data)
        self.assertNotIn('target_epitope_residues',data['nanohunter'])
        self.assertEqual(data['sequences'][1]['protein']['msa'],'empty')
        self.assertEqual(self.template.read_bytes(),original)
        self.spec['refinement_engine']='boltz'
        with self.assertRaisesRegex(ValueError,'changed'):io.refinement_template(self.spec,output)
    def test_full_preserves_absolute_msa(self):
        self.spec['refinement_engine']='esmfold2-full-mlx'
        output=self.root/'full.yaml';io.refinement_template(self.spec,output)
        self.assertEqual(io.yaml.safe_load(output.read_text())['sequences'][1]['protein']['msa'],str((self.root/'target.a3m').resolve()))
    def test_missing_seed_cannot_resume(self):
        io.handoff(self.spec,self.source,self.output)
        (self.output/'run_001/cycle_00/pred_min/model_0.pdb').unlink()
        with self.assertRaises(OSError):stages.verify_handoff(self.output)
    def test_missing_or_invalid_hallucination_confidence_cannot_commit(self):
        self.spec.update(method='hallucination', initial_engine='boltz')
        original=self.source/'run_001/cycle_00'
        pdb(original/'pred_min/model_0.pdb')
        (original/'boltz_input.yaml').write_bytes(self.template.read_bytes())
        with self.assertRaises(OSError):io.handoff(self.spec,self.source,self.output)
        for confidence in [{}, {'iptm': float('nan')}, {'iptm': True}]:
            (original/'pred_min/confidence.json').write_text(json.dumps(confidence))
            with self.assertRaisesRegex(ValueError,'confidence'):io.handoff(self.spec,self.source,self.output)
            self.assertFalse((self.output/'initialization.json').exists())
        (original/'pred_min/confidence.json').write_text('{"iptm": 0.5}')
        io.handoff(self.spec,self.source,self.output)
        self.assertEqual(stages.verify_handoff(self.output)['initial_engine'],'boltz')


class RoutingTests(unittest.TestCase):
    def test_invalid_routes_rejected(self):
        for args in [
            ['--initialization-method','rfd3','--workflow','nanobody'],
            ['--initialization-method','hallucination','--predictor','esmfold2-fast-mlx'],
            ['--initialization-method','nope'],
            ['--initialization-predictor'],
            ['--initialization-method','rfd3','--initialization-method','rfd3'],
            ['--initialization-method','hallucination','--initial-structure','x.pdb'],
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):stages.validate(args)
    def test_separate_engines(self):
        self.assertEqual(stages.validate(['--initialization-method','hallucination','--initialization-predictor','boltz','--predictor','esmfold2-fast-mlx']),('hallucination','boltz','esmfold2-fast-mlx'))
    def test_check_config_never_predicts_or_writes_run(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);template=root/'input.yaml';template.write_text('sequences: []')
            for engine in ['boltz','esmfold2-fast-mlx']:
                py=stages.engine_python(root,engine);py.parent.mkdir(parents=True,exist_ok=True);py.touch()
            args=['--initialization-method','hallucination','--initialization-predictor','boltz','--predictor','esmfold2-fast-mlx','--out-root',str(root),'--run-name','untouched','--template-yaml',str(template),'--check-config']
            calls=[]
            with patch.dict(os.environ,NANOHUNTER_ROOT=str(root)),patch.object(stages.subprocess,'run',side_effect=lambda cmd,**kw:calls.append(cmd)):
                stages.main(args)
            self.assertFalse((root/'untouched').exists())
            shells=[c for c in calls if c[0]=='/bin/bash']
            self.assertEqual(len(shells),2)
            self.assertTrue(all('--check-config' in c for c in shells))
            self.assertFalse(any('handoff' in c or 'rfd3' in c for c in calls))


if __name__=='__main__':unittest.main()
