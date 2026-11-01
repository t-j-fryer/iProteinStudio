"""Settings, family allocation and predictor adapter contracts; no model calls."""
import csv,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
PIPE=ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0,str(PIPE/'scripts'))
from rfd4.contract import normalize,allocated_lengths,family_config,filter_verdict,predictor_identity,PREDICTORS
from rfd4.predictors import runtime_spec,session_config,prediction_files

class Configuration(unittest.TestCase):
    def test_equal_allocation_spans_range_and_interleaves(self):
        cases=[(5,[75,76,77,78,79]),(2,[75,79]),(1,[77]),(12,[75,76,77,78,79,75,76,77,78,79,75,76])]
        for count,want in cases:
            cfg=normalize(dict(count=count,length_plan=dict(minimum=75,maximum=79)))
            self.assertEqual(allocated_lengths(cfg),want)
        cfg=normalize(dict(count=6,length_plan=dict(minimum=75,maximum=150,counts={'75':2,'120':3,'150':1})))
        self.assertEqual(allocated_lengths(cfg),[75,120,150,75,120,120])
        config=dict(settings=cfg,annotated_cif='old',length_inputs={'75':'a','120':'b','150':'c'})
        self.assertEqual(family_config(config,2)['annotated_cif'],'c')
        self.assertEqual(family_config(config,2)['settings']['length'],150)
        self.assertEqual(cfg['length'],120) # source request remains immutable
        with self.assertRaises(ValueError):family_config(dict(config,length_inputs={}),2)
    def test_allocation_rejects_ambiguous_or_invalid_requests(self):
        for plan in [dict(minimum=120,maximum=75),dict(minimum=0,maximum=100),dict(minimum=75,maximum=120,counts={'75':2}),dict(minimum=75,maximum=120,counts={'075':1}),dict(minimum=75,maximum=120,counts={'75':True})]:
            with self.subTest(plan=plan),self.assertRaises(ValueError):normalize(dict(length_plan=plan))
        with self.assertRaises(ValueError):normalize(dict(task='nanobody',source='x',scaffold_id='7xl0_vobarilizumab',length_plan=dict(minimum=75,maximum=120)))
    def test_filters_are_conjunctive_fail_closed_and_do_not_select_parents(self):
        cfg=normalize(dict(task='protein',source='x',assess_native=True,target_msa='empty',hit_filters={'ipsae_min':.5,'iptm':.6}))
        self.assertTrue(filter_verdict(cfg,{'ipsae_min':.5,'iptm':.6})['hit_filter_passed'])
        self.assertFalse(filter_verdict(cfg,{'ipsae_min':.9})['hit_filter_passed'])
        self.assertFalse(filter_verdict(cfg,{'ipsae_min':float('nan'),'iptm':.9})['hit_filter_passed'])
        self.assertEqual(filter_verdict({},{}),{})
        for filters in [{'ipsae_min':2},{'ipsae_min':True},{'not_a_metric':.5}]:
            with self.assertRaises(ValueError):normalize(dict(cfg,hit_filters=filters))
    def test_predictors_map_to_their_actual_runtime_and_profile(self):
        expected={'boltz':('boltz','boltz2'),'intellifold':('intellifold','v2-flash'),'intellifold-full':('intellifold','v2'),'protenix-v2':('protenix','protenix-v2'),'protenix-mini':('protenix','protenix-mini'),'protenix-constraint-v0.5':('protenix_constraint','protenix-constraint-v0.5'),'openfold-3-mlx':('openfold3_mlx','openfold3')}
        for name in PREDICTORS:
            normalize(dict(task='protein',source='x',search='iterative',predictor=name,target_msa='empty'))
            identity=predictor_identity(name)
            if name in expected:self.assertEqual((identity['runtime'],identity['model']),expected[name])
            python,env=runtime_spec('/tmp/runtime',name)
            self.assertIn('NanoHunter_'+identity['runtime'],str(python))
            if name.startswith('intellifold'):self.assertEqual(env['OMP_NUM_THREADS'],'1')
        with tempfile.TemporaryDirectory() as raw:
            p=Path(raw)/'query.yaml';p.write_text('version: 1\nsequences:\n  - protein: {id: A, sequence: AAA, msa: empty}\n')
            for name in PREDICTORS:
                cfg=session_config('/tmp/runtime',name,p,Path(raw)/'work',42)
                self.assertEqual(cfg['samples'],1);self.assertFalse(cfg['use_msa'])
                self.assertEqual(cfg['seed'],'42')
            self.assertEqual(session_config('/tmp/runtime','openfold-3-mlx',p,raw,42)['engine_args'],[])
    def test_catalogue_scaffolds_match_exact_sequences_cdrs_and_hashes(self):
        import hashlib
        catalogue=PIPE/'examples/nanobody_scaffolds'
        rows=list(csv.DictReader((catalogue/'catalog.tsv').read_text().splitlines(),delimiter='\t'))
        provenance=json.loads((catalogue/'structures/PROVENANCE.json').read_text())
        letters=dict(zip('ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN PRO GLN ARG SER THR VAL TRP TYR'.split(),'ACDEFGHIKLMNPQRSTVWY'))
        self.assertEqual(len(rows),8)
        for row in rows:
            path=catalogue/'structures'/(row['scaffold_id']+'.pdb')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),provenance[row['scaffold_id']]['sha256'])
            ca=[line for line in path.read_text().splitlines() if line.startswith('ATOM') and line[12:16].strip()=='CA']
            self.assertEqual(''.join(letters[line[17:20]] for line in ca),row['sequence'])
            for n in range(1,4):
                first,last=map(int,row[f'cdr{n}_range_1based'].split('-'))
                self.assertTrue(1<=first<=last<=len(ca))
            cfg=normalize(dict(task='nanobody',source='target.pdb',scaffold_id=row['scaffold_id']))
            self.assertEqual(cfg['cdr_ranges'],','.join(f"CDR{i}:"+row[f'cdr{i}_range_1based'] for i in (1,2,3)))
    def test_mixed_target_entities_are_not_silently_dropped(self):
        import biotite.structure as bs
        from rfd4.prepare import require_protein_target
        atoms=bs.AtomArray(2);atoms.res_name=['ALA','HOH'];atoms.element=['C','O']
        require_protein_target(atoms)
        atoms.res_name=['ALA','ZN'];atoms.element=['C','Zn']
        with self.assertRaisesRegex(ValueError,'non-protein entities'):require_protein_target(atoms)
    def test_legacy_request_has_same_single_length_and_no_filter(self):
        cfg=normalize({'length':92,'count':3})
        self.assertEqual(allocated_lengths(cfg),[92]*3)
        self.assertIsNone(cfg['hit_filters'])
    def test_adapter_artifact_mapping_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            leaf=Path(raw)/'query/pred_min';leaf.mkdir(parents=True)
            with self.assertRaises(ValueError):prediction_files(raw,'query')
            (leaf/'model_0.cif').write_text('coordinates');(leaf/'confidence.json').write_text('{}')
            self.assertEqual(prediction_files(raw,'query'),(leaf/'model_0.cif',leaf/'confidence.json'))

if __name__=='__main__':unittest.main()
