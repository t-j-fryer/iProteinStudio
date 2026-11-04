"""Selection, allocation and preparation contracts for shared design controls."""
import json, math, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
PIPE=ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0,str(PIPE/'scripts'))
from rfd4.contract import normalize, selection_score, selection_metric, allocated_scaffolds, allocated_conformers, family_config, select

class DesignControls(unittest.TestCase):
    def test_requested_metric_changes_survivor_and_missing_is_not_substituted(self):
        first={'ipsae_min':.9,'iptm':.3};second={'ipsae_min':.2,'iptm':.8}
        cfg=normalize(dict(task='protein',source='target',search='beam',target_msa='empty',selection_metric='iptm'))
        rows=[dict(id=str(i),score=selection_score(cfg,m)) for i,m in enumerate([first,second])]
        self.assertEqual(select(rows,1)[0]['id'],'1')
        for metrics in ({'ipsae_min':.9},{'iptm':math.nan},{'iptm':2},{'iptm':True}):
            with self.assertRaises(ValueError): selection_score(cfg,metrics)
        self.assertEqual(selection_metric(dict(task='protein')),'ipsae_min')
        self.assertEqual(selection_metric(dict(task='ligand')),'pbind_ligand_plddt')
    def test_ligand_objective_and_engine_capabilities(self):
        base=dict(task='ligand',ligand_smiles='CCO',search='beam',sequence_model='lasermpnn',predictor='boltz')
        for metric,want in [('pbind_ligand_plddt',1.5),('pbind',.7),('ligand_plddt',80)]:
            cfg=normalize(dict(base,selection_metric=metric))
            self.assertEqual(selection_score(cfg,{'pbind':.7,'ligand_plddt':80}),want)
        for engine in ('esmfold2-fast-mlx','esmfold2-full-mlx','esmfold2-600-mlx'):
            cfg=normalize(dict(base,predictor=engine,selection_metric='ligand_plddt'))
            self.assertEqual(selection_score(cfg,{'ligand_plddt':80}),80)
            with self.assertRaises(ValueError): normalize(dict(base,predictor=engine))
        with self.assertRaises(ValueError):normalize(dict(base,selection_metric='ipsae_min'))
    def test_framework_allocation_is_deterministic_and_keeps_per_framework_cdrs(self):
        weights={'7xl0_vobarilizumab':2,'7eow_caplacizumab':1}
        cfg=normalize(dict(task='nanobody',source='target',count=6,scaffold_weights=weights,scaffold_msa='auto'))
        starts=allocated_scaffolds(cfg)
        self.assertEqual(starts.count('7xl0_vobarilizumab'),4)
        self.assertEqual(starts.count('7eow_caplacizumab'),2)
        self.assertEqual(starts,allocated_scaffolds(dict(cfg,scaffold_weights=dict(reversed(list(weights.items()))))))
        config=dict(settings=cfg,scaffold_inputs={key:dict(annotated_cif=key+'.cif') for key in weights})
        children=[family_config(config,i) for i in range(6)]
        for child,key in zip(children,starts):
            self.assertEqual(child['annotated_cif'],key+'.cif');self.assertEqual(child['settings']['scaffold_id'],key)
            self.assertIsNone(child['settings']['scaffold_weights'])
        self.assertNotEqual(children[0]['settings']['cdr_ranges'],children[1]['settings']['cdr_ranges'])
        for bad in ({},{'unknown':1},{'7xl0_vobarilizumab':0},{'7xl0_vobarilizumab':True}):
            with self.assertRaises(ValueError): normalize(dict(cfg,scaffold_weights=bad))
    def test_framework_alignment_switches_with_each_family_and_is_cached_separately(self):
        from rfd4.search_engine import Engine
        cfg=normalize(dict(task='nanobody',source='target',count=2,scaffold_weights={'7xl0_vobarilizumab':1,'7eow_caplacizumab':1},scaffold_msa='auto'))
        config=dict(settings=cfg,scaffold_inputs={key:dict(annotated_cif=key+'.cif') for key in cfg['scaffold_weights']})
        engine=object.__new__(Engine);engine.campaign_config=config;engine.framework_configs={};engine.output=Path('/tmp/fixture')
        calls=[]
        def resolve(current):
            calls.append(current['output'])
            return dict(current,settings=dict(current['settings'],scaffold_msa=current['output']+'/framework.a3m'))
        with patch('rfd4.msas.resolve',side_effect=resolve):
            engine.configure_family(0);first=engine.cfg['scaffold_msa'];first_ranges=engine.cfg['cdr_ranges']
            engine.configure_family(1);second=engine.cfg['scaffold_msa']
            self.assertNotEqual(first,second);self.assertNotEqual(first_ranges,engine.cfg['cdr_ranges'])
            engine.configure_family(0);self.assertEqual(engine.cfg['scaffold_msa'],first)
            self.assertEqual(len(calls),2)

    def test_conformer_and_length_allocation_select_exact_authored_input(self):
        rows=[dict(label='A',path='a.sdf',weight=.75),dict(label='B',path='b.sdf',weight=.25)]
        cfg=normalize(dict(task='ligand',ligand_smiles='CCO',count=8,ligand_conformers=rows,length_plan=dict(minimum=75,maximum=76)))
        self.assertEqual([r['label'] for r in allocated_conformers(cfg)].count('A'),6)
        config=dict(settings=cfg,ligand_inputs={label:{str(n):f'{label}-{n}' for n in (75,76)} for label in ('A','B')})
        for i,row in enumerate(allocated_conformers(cfg)):
            child=family_config(config,i)
            self.assertEqual(child['annotated_cif'],f"{row['label']}-{75+i%2}")
            self.assertEqual(child['settings']['ligand_conformer'],row['path'])
        with self.assertRaises(ValueError):normalize(dict(cfg,source='external.cif'))
    def test_atom_conditions_translate_to_pinned_native_enums(self):
        from rfd4.prepare import condition_spec
        import numpy as np
        from types import SimpleNamespace
        atoms=SimpleNamespace(chain_id=np.array(['B']*3),res_id=np.array([1]*3),atom_name=np.array(['C1','C2','O3']))
        cfg=normalize(dict(task='ligand',ligand_smiles='CCO',ligand_atom_conditions={'C1':['buried','hotspot'],'C2':['exposed'],'O3':['hbondDonor','hbondAcceptor']}))
        spec=condition_spec(cfg,'molecule.cif',atoms)['conditions']
        self.assertIn(1,spec['C_RAS']);self.assertIn(3,spec['C_RAS']);self.assertIn(3,spec['C_HB'])
        self.assertIn('C1',spec['C_HOT'][True][0]['select'])
        with self.assertRaises(ValueError):normalize(dict(cfg,ligand_atom_conditions={'C1':['exposed','hotspot']}))
        with self.assertRaises(ValueError):condition_spec(dict(cfg,ligand_atom_conditions={'N9':['buried']}),'molecule.cif',atoms)
    def test_ligand_confidence_adapter_never_requests_affinity(self):
        from rfd4.ligand_score import Engine
        from types import SimpleNamespace
        engine=object.__new__(Engine)
        engine.config={'settings':dict(task='ligand',predictor='esmfold2-fast-mlx',selection_metric='ligand_plddt',ligand_smiles='CCO')}
        engine.predictor='esmfold2-fast-mlx'
        class Backend:
            @staticmethod
            def audit_structure(*args): pass
            def fold(self,seqs,smiles,directory,args,pocket):
                return {key:SimpleNamespace(pdb=str(structure),pbind=None,ligand_plddt=82) for key in seqs}
            def affinity(self,*args): raise AssertionError('Confidence-only prediction requested affinity')
        engine.backend=Backend()
        with tempfile.TemporaryDirectory() as raw,patch.dict(sys.modules,runtime=SimpleNamespace(Backend=Backend)):
            engine.output=Path(raw);structure=engine.output/'model.pdb';structure.write_text('fixture')
            rows=engine.score_sequences('family',{'candidate':'AAA'})
            self.assertEqual(rows['candidate']['score'],82)
            self.assertEqual(rows['candidate']['metrics'],{'ligand_plddt':82})
            self.assertEqual(len(rows['candidate']['receipts']),1)

    def test_preflight_uses_saved_pipeline_instead_of_installed_runner(self):
        import os, shutil, subprocess
        from unittest.mock import patch
        sys.path.insert(0,str(PIPE/'mcp'))
        from iprotein_mcp.rfd4 import prepare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();out=root/'projects/demo/rfd4_runs/test'
            pipeline=out/'.studio_runtime/pipeline'
            for rel in ('scripts/rfd4_cli.py','scripts/rfd4/contract.py'):
                path=pipeline/rel;path.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(PIPE/rel,path)
            for rel in ('scripts/rfd4_cli.py','venvs/NanoHunter_rfd4/bin/python',
                        'components/rfd4/current/runtime.json',
                        'models/rfd4/diffusers/transformer/diffusion_pytorch_model.safetensors',
                        'models/rfd4/diffusers/vae/diffusion_pytorch_model.safetensors'):
                path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('inert fixture')
            commands=[]
            def run(command,**kwargs):
                commands.append(command)
                for name in ('annotated.cif','condition_spec.json','feature_audit.json'):
                    (out/name).write_text('{}')
                return subprocess.CompletedProcess(command,0,'','')
            with patch.dict(os.environ,{'NANOHUNTER_ROOT':str(root)}), patch('iprotein_mcp.rfd4.subprocess.run',side_effect=run):
                context,provenance=prepare(out,dict(task='monomer',length=65,count=2))
            self.assertEqual([c[3] for c in commands],['author','audit'])
            self.assertTrue(all(c[2]==str(pipeline/'scripts/rfd4_cli.py') for c in commands))
            self.assertEqual(context['pipeline_snapshot'],str(pipeline))
            self.assertIn(str(root/'scripts/rfd4_cli.py'),context['steps'][0]['command'])
            self.assertIn(str(pipeline/'scripts/rfd4_cli.py'),[p['path'] for p in provenance])
            self.assertEqual((root/'scripts/rfd4_cli.py').read_text(),'inert fixture')

    def test_cli_round_trip_and_schema_cover_new_fields(self):
        import subprocess
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'request.json';path.write_text(json.dumps(dict(task='protein',source='target',search='beam',target_msa='empty',selection_metric='iptm')))
            result=subprocess.run([sys.executable,str(PIPE/'scripts/rfd4_cli.py'),'validate','--root',raw,'--config',str(path),'--output',raw],capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout)['settings']['selection_metric'],'iptm')
        properties=json.loads((PIPE/'mcp/schemas/rfd4-v1.json').read_text())['properties']['request']['properties']
        self.assertEqual(set(properties),set(normalize({})))

if __name__=='__main__':unittest.main()
