"""Execute real stage scoping, cycle YAML generation, and Protenix conversion on CPU."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / 'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0, str(PIPE / 'scripts'))
import hunter_stages as stages
import hunter_initialization_io as io
import protenix_predict as protenix
import esmfold2_predict as esmfold2

class EpitopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.template = self.root / 'input.yaml'
        self.template.write_text('''version: 1
nanohunter:
  target_epitope_residues: [B2]
  protenix_pocket_max_distance: 8.0
sequences:
  - protein:
      id: A
      sequence: AAAAAA
      msa: empty
  - protein:
      id: B
      sequence: HIKLMN
      msa: empty
''')
        source = (PIPE / 'nanohunter_run.sh').read_text()
        start = source.index('make_yaml_with_binder_sequence()')
        end = source.index('\nPY\n}', start) + len('\nPY\n}')
        self.shell = self.root / 'rewrite.sh'
        self.shell.write_text(source[start:end] + '\nmake_yaml_with_binder_sequence "$@"\n')
    def tearDown(self): self.tmp.cleanup()
    def rewrite(self, engine, cycle, policy='auto', phase='design', template=None):
        output = self.root / 'output.yaml'
        env = dict(os.environ, PIPELINE_CODE_ROOT=str(PIPE),
                   TARGET_EPITOPE_RESIDUES='B3', BOLTZ_CONTACT_DISTANCE='6',
                   BOLTZ_CONTACT_FORCE='1', BOLTZ_CONTACT_MODE='pocket',
                   NANOBODY_SEED_CDR_RANGES='', TARGET_TEMPLATE_MODE='guide',
                   TARGET_TEMPLATE_THRESHOLD='2', TARGET_TEMPLATE_SHA256='',
                   INTELLIFOLD_TARGET_TEMPLATE_MANIFEST='', REFINEMENT_EPITOPE_GUIDANCE=policy)
        env.pop('IPROTEINSTUDIO_HUNTER_HANDOFF', None)
        subprocess.run(['bash', str(self.shell), str(template or self.template), str(output),
                        'CCCCCC', '', engine, '', phase, str(cycle)], env=env, check=True)
        return io.yaml.safe_load(output.read_text()), output
    def test_boltz_cycle_scope(self):
        for cycle, policy, expected in [(0,'off',True), (1,'off',False), (5,'auto',True)]:
            with self.subTest(cycle=cycle, policy=policy):
                data,_ = self.rewrite('boltz',cycle,policy)
                self.assertEqual(bool(data.get('constraints')),expected)
                if expected:
                    pocket=data['constraints'][0]['pocket']
                    self.assertEqual(pocket['contacts'],[['B',3]])
                    self.assertEqual(pocket['max_distance'],6)
                    self.assertTrue(pocket['force'])
    def test_protenix_cli_override_and_cycle_scope(self):
        for cycle,policy,expected in [(0,'off',True),(1,'off',False),(3,'auto',True)]:
            data,path=self.rewrite('protenix-constraint-v0.5',cycle,policy)
            self.assertEqual(bool(data.get('nanohunter')),expected)
            if expected:
                self.assertEqual(data['nanohunter']['target_epitope_residues'],['B3'])
                job,_,_=protenix.convert_yaml(path,constraint_model=True)
                self.assertIn('constraint',job)
            else:
                job,_,_=protenix.convert_yaml(path,constraint_model=True)
                self.assertNotIn('constraint',job)
    def test_post_checks_blind(self):
        for engine in ['boltz','protenix-constraint-v0.5']:
            data,_=self.rewrite(engine,2,phase='post')
            self.assertNotIn('constraints',data)
            self.assertNotIn('nanohunter',data)
    def test_cross_engine_stage_matrix(self):
        for method, initial in [('rfd3','rfd3'),('hallucination','boltz'),('hallucination','protenix-constraint-v0.5'),('hallucination','intellifold')]:
            for refine in ['boltz','protenix-constraint-v0.5','esmfold2-full-mlx']:
                for policy in ['auto','off']:
                    with self.subTest(method=method,initial=initial,refine=refine,policy=policy):
                        spec=dict(method=method,initial_engine=initial,refinement_engine=refine,
                                  arguments=['--template-yaml',str(self.template),'--refinement-epitope-guidance',policy])
                        path=self.root/'scoped.yaml';path.unlink(missing_ok=True)
                        io.refinement_template(spec,path)
                        data=io.yaml.safe_load(path.read_text())
                        guided=policy=='auto' and refine in {'boltz','protenix-constraint-v0.5'}
                        self.assertEqual(bool(data.get('nanohunter',{}).get('target_epitope_residues')),guided)
                        if method=='hallucination':
                            path.unlink()
                            io.refinement_template(spec,path,initial=True)
                            self.assertEqual(bool(io.yaml.safe_load(path.read_text()).get('nanohunter',{}).get('target_epitope_residues')),initial!='intellifold')
    def test_rfd3_translates_chain_and_noncontiguous_numbering(self):
        result=io.rfd3_hotspots('B:2 C1 B2', {'B':'AAA','C':'GG'}, ['F','T'],
                               {'F':{101:'ALA',105:'ALA',110:'ALA'},'T':{23:'GLY',24:'GLY'}})
        self.assertEqual(result,{'F105':['hotspot'],'T23':['hotspot']})
        for sites in ['A1','B0','B4','D1']:
            with self.assertRaises(ValueError):
                io.rfd3_hotspots(sites,{'B':'AAA'},['F'],{'F':{101:'ALA',105:'ALA',110:'ALA'}})

    def test_esmfold_handoff_parses_without_generation_metadata(self):
        for model in ('fast', 'full'):
            for alias in ('nanohunter', 'nano_hunter', 'NanoHunter'):
                for metadata in ({}, {'target_epitope_residues': ['B2']},
                                 {'target_epitope_residues': ['B2'], 'protenix_pocket_max_distance': 8.0}):
                    with self.subTest(model=model, alias=alias, metadata=metadata):
                        data = io.yaml.safe_load(self.template.read_text())
                        for key in ('nanohunter', 'nano_hunter', 'NanoHunter'):
                            data.pop(key, None)
                        data[alias] = metadata
                        self.template.write_text(io.yaml.safe_dump(data, sort_keys=False))
                        original = self.template.read_bytes()
                        spec = dict(method='rfd3', initial_engine='rfd3',
                                    refinement_engine='esmfold2-' + model + '-mlx',
                                    arguments=['--template-yaml', str(self.template)])
                        path = self.root / 'esmfold-handoff.yaml'
                        path.unlink(missing_ok=True)
                        io.refinement_template(spec, path)
                        chains, _ = esmfold2.read_input(path, model)
                        self.assertEqual([c['sequence'] for c in chains], ['AAAAAA', 'HIKLMN'])
                        self.assertEqual(self.template.read_bytes(), original)
                        self.assertNotIn('nanohunter', io.yaml.safe_load(path.read_text()))

    def test_empty_metadata_removed_when_supported_refiner_guidance_disabled(self):
        data = io.yaml.safe_load(self.template.read_text())
        data['nanohunter'] = {'target_epitope_residues': ['B2']}
        self.template.write_text(io.yaml.safe_dump(data, sort_keys=False))
        for engine in ('boltz', 'protenix-constraint-v0.5'):
            spec = dict(method='rfd3', initial_engine='rfd3', refinement_engine=engine,
                        arguments=['--template-yaml', str(self.template), '--refinement-epitope-guidance', 'off'])
            path = self.root / (engine + '.yaml')
            io.refinement_template(spec, path)
            self.assertNotIn('nanohunter', io.yaml.safe_load(path.read_text()))
    def test_stage_cli_scope(self):
        args=['--target-epitope-residues','B2','--refinement-epitope-guidance','off']
        self.assertIn('--target-epitope-residues',stages.stage_arguments(args,'boltz',initial=True))
        self.assertNotIn('--target-epitope-residues',stages.stage_arguments(args,'boltz'))
        self.assertNotIn('--target-epitope-residues',stages.stage_arguments(args,'intellifold',initial=True))

    def test_mcp_accepts_and_validates_policy(self):
        sys.path.insert(0,str(PIPE/'mcp'))
        from iprotein_mcp import plans, common
        base=['--workflow','minibinder','--predictor','boltz','--sequence-designer','solublempnn',
              '--num-runs','1','--num-opt-cycles','2','--iptm-threshold','0.7']
        for policy in ['auto','off']:
            args=base+['--refinement-epitope-guidance',policy]
            self.assertEqual(plans._normalize_iterative_arguments(args)[0],args)
        with self.assertRaises(common.StudioError):
            plans._normalize_iterative_arguments(base+['--refinement-epitope-guidance','sometimes'])

    def test_invalid_policy_rejected(self):
        with self.assertRaisesRegex(ValueError,'auto or off'):
            stages.validate(['--refinement-epitope-guidance','sometimes'])
        with self.assertRaisesRegex(ValueError,'Missing or repeated'):
            stages.validate(['--refinement-epitope-guidance'])

if __name__=='__main__':unittest.main()
