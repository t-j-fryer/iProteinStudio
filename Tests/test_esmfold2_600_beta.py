"""Fail-closed authoring, asset selection and memory-control contracts."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(S),str(S.parent/'mcp')]
import esmfold2_600,esmfold2_predict,prediction_profiles,setup_portable
from iprotein_mcp import plans
class Beta(unittest.TestCase):
 def test_new_installer_does_not_require_six_billion_weights(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();base=root/'components/esmfold2/current';base.mkdir(parents=True);(base/'runtime.json').write_text(json.dumps({'engine':'esmfold2'}))
   with patch.object(setup_portable,'from_catalog',return_value=base) as runtime,patch.object(setup_portable,'download') as download:
    setup_portable.install(root,'esmfold2_600')
   runtime.assert_called_once_with(root,'esmfold2')
   paths=[c.args[1]['path'] for c in download.call_args_list]
   self.assertFalse(any('ESMC-6B' in p for p in paths));self.assertTrue(any('ESMplusplus-large' in p for p in paths))
   self.assertTrue(json.loads((root/'receipts/esmfold2_600.json').read_text())['complete'])
 def test_encoder_remapping_is_lossless_and_unknown_keys_fail(self):
  raw={'embed.weight':object(),'transformer.blocks.0.attn.layernorm_qkv.0.weight':object(),'sequence_head.3.bias':object()}
  got=esmfold2_600.remap_encoder(raw)
  self.assertIs(got['esmc.embed.weight'],raw['embed.weight']);self.assertEqual(len(got),len(raw))
  self.assertIs(got['esmc.transformer.blocks.0.attn.ln_qkv.weight'],raw['transformer.blocks.0.attn.layernorm_qkv.0.weight'])
  with self.assertRaisesRegex(ValueError,'Unknown'):esmfold2_600.remap_encoder({'unexpected.weight':object()})
 def test_memory_controls_are_explicit_and_validated(self):
  defaults=prediction_profiles.normalize();full=defaults['esmfold2-full-mlx'];self.assertEqual(full['chunk_size'],0);self.assertEqual(full['cache_limit_mib'],4096)
  changed=prediction_profiles.normalize({'esmfold2-full-mlx':{'chunk_size':32,'cache_limit_mib':512}})
  self.assertNotEqual(full,changed['esmfold2-full-mlx'])
  for values in ({'chunk_size':-1},{'cache_limit_mib':True},{'cache_limit_mib':4097},{'msa_depth':1}):
   with self.assertRaises(ValueError):prediction_profiles.normalize({'esmfold2-600-mlx':values})
 def test_complete_complexes_and_ligands_but_no_msa_x_or_guidance(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'one.yaml';base={'sequences':[{'protein':{'id':'A','sequence':'ACDEFG','msa':'empty'}}]}
   for extra in ({'protein':{'id':'B','sequence':'ACDEFG','msa':'empty'}},{'ligand':{'id':'B','smiles':'CO'}}):
    d=copy.deepcopy(base);d['sequences'].append(extra);p.write_text(json.dumps(d))
    self.assertEqual(len(esmfold2_predict.read_input(p,'600')[0]),2)
   for kind in ('msa','x','templates','properties'):
    d=copy.deepcopy(base)
    if kind=='msa':d['sequences'][0]['protein']['msa']='auto'
    elif kind=='x':d['sequences'][0]['protein']['sequence']='AXDEFG'
    else:d[kind]=[{}]
    p.write_text(json.dumps(d))
    with self.assertRaises(ValueError):esmfold2_predict.read_input(p,'600')
    if kind!='x':self.assertEqual(len(esmfold2_predict.read_input(p,'600',True)[0]),1)
 def test_plan_accepts_campaign_predictor_and_complete_complexes(self):
  self.assertIn('esmfold2-600-mlx',plans.PREDICTORS)
  base={'project':'test','request':{'predictors':['esmfold2-600-mlx'],'jobs':[{'name':'one','chains':[{'id':'A','kind':'protein','sequence':'ACDEFG','msa':'auto'},{'id':'B','kind':'ligand','smiles':'CO'}]}]}}
  with tempfile.TemporaryDirectory() as t,patch.object(plans,'project_root',return_value=Path('/unused')),patch.object(plans,'runtime_root',return_value=Path(t)),patch.object(plans,'_persist',side_effect=lambda *args:args),patch.object(plans,'_script_provenance',return_value=[]):
   result=plans._prediction_plan(base,'prediction','predictions','test');self.assertEqual(result[2]['config']['predictors'],['esmfold2-600-mlx'])
   for chains in (None,[None],[dict(id='A',kind='protein',sequence='AXDEFG',msa='empty')],[dict(id='A',kind='protein',sequence='ACDEFG',msa='file.a3m')]):
    bad=copy.deepcopy(base);bad['request']['jobs'][0]['chains']=chains
    with self.assertRaises(Exception):plans._prediction_plan(bad,'prediction','predictions','test')
   bad=copy.deepcopy(base);bad['request']['affinity']=True
   with self.assertRaisesRegex(Exception,'affinity'):plans._prediction_plan(bad,'prediction','predictions','test')
 def test_exact_variant_and_registry_identity(self):
  from engine_adapters import command_for
  from engine_registry import descriptor
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);cmd,env=command_for('esmfold2-600-mlx',root/'in.yaml',root/'out',root,'v2-flash',root)
   self.assertEqual(cmd[cmd.index('--model')+1],'600');self.assertIn('--unrestrained-check',cmd)
   self.assertEqual(env['HF_HUB_OFFLINE'],'1')
   d=descriptor('esmfold2-600-mlx');self.assertEqual(d['session'],'ESMFold2Session');self.assertEqual(d['capabilities'],['structure'])
 def test_nise_complete_sequence_folding_and_affinity_separation(self):
  from nise.contract import normalize
  for objective in ('nesso','psichic'):
   cfg=normalize(dict(smiles='CO',folding_engine='esmfold2-600-mlx',scoring_mode='screening',screening_engine=objective,nesso_screen=True,phase0_nesso_screen=True,final_predictors=['esmfold2-600-mlx']))
   self.assertEqual(cfg['folding_engine'],'esmfold2-600-mlx');self.assertEqual(cfg['resident_workers'],0)
  with self.assertRaisesRegex(ValueError,'requires'):normalize(dict(smiles='CO',folding_engine='esmfold2-600-mlx'))
 def test_rfd4_refinement_contract_and_sequence_only_msa(self):
  from rfd4.contract import normalize
  for policy in ('fixed','iterative','greedy','beam'):
   cfg=normalize(dict(task='protein',source='target.pdb',search=policy,predictor='esmfold2-600-mlx'))
   self.assertEqual(cfg['predictor'],'esmfold2-600-mlx')
 def test_all_prediction_schema_enums_include_600(self):
  def walk(x):
   if isinstance(x,dict):
    if 'enum' in x and 'esmfold2-fast-mlx' in x['enum']:self.assertIn('esmfold2-600-mlx',x['enum'])
    for v in x.values():walk(v)
   elif isinstance(x,list):
    for v in x:walk(v)
  for p in (S.parent/'mcp/schemas').glob('*.json'):walk(json.loads(p.read_text()))
 def test_resident_session_uses_600_for_loading_and_later_requests(self):
  import resident_predictor
  with tempfile.TemporaryDirectory() as t,patch.dict(sys.modules,{'torch':object()}),patch.object(esmfold2_predict,'Session') as model,patch.object(esmfold2_predict,'run') as run:
   root=Path(t);source=root/'inputs';source.mkdir();(source/'one.yaml').write_text('{}')
   session=resident_predictor.ESMFold2Session(dict(root=t,engine='esmfold2-600-mlx'))
   model.assert_called_once_with(root,'600');session.predict(source,root/'out',1)
   self.assertEqual(run.call_args.args[1],'600');self.assertIs(run.call_args.kwargs['session'],model.return_value)
 def test_nise_final_command_keeps_600_identity(self):
  import importlib.util
  sys.path.insert(0,str(S/'nise'))
  spec=importlib.util.spec_from_file_location('test600_final',S/'nise/final_checks.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as t,patch.object(module,'shortlist',return_value=[dict(name='one',sequence='ACDEFG',score=.8)]),patch.object(module.subprocess,'run') as run:
   root=Path(t);module.run(root,root/'out',dict(top_x=1,final_predictors=['esmfold2-600-mlx'],seed=42),'CCO')
   cmd=run.call_args.args[0];self.assertEqual(cmd[cmd.index('--model')+1],'600')
 def test_profile_schema_present_in_every_existing_esm_profile_map(self):
  def walk(x):
   if isinstance(x,dict):
    if 'esmfold2-fast-mlx' in x:
     self.assertIn('esmfold2-600-mlx',x)
     self.assertEqual(x['esmfold2-600-mlx']['properties']['msa_depth']['maximum'],0)
     self.assertIn('chunk_size',x['esmfold2-600-mlx']['properties'])
    for v in x.values():walk(v)
   elif isinstance(x,list):
    for v in x:walk(v)
  for p in (S.parent/'mcp/schemas').glob('*.json'):walk(json.loads(p.read_text()))
 def test_custom_prediction_recipe_accepts_600_and_memory_controls(self):
  from iprotein_mcp import composition
  parameters={'project':'test','request':{'predictors':['esmfold2-600-mlx'],'jobs':[{'name':'one','chains':[{'id':'A','kind':'protein','sequence':'ACDEFG','msa':'empty'}]}],'prediction_settings':{'esmfold2-600-mlx':{'chunk_size':32,'cache_limit_mib':512}}}}
  with tempfile.TemporaryDirectory() as t,patch.object(plans,'project_root',return_value=Path('/unused')),patch.object(plans,'runtime_root',return_value=Path(t)),patch.object(plans,'_persist',side_effect=lambda *args:args),patch.object(plans,'_script_provenance',return_value=[]):
   result=composition.recipe_plan(dict(schema_version=2,route='prediction',parameters=parameters))
   cfg=result[2]['config'];self.assertEqual(cfg['predictors'],['esmfold2-600-mlx']);self.assertEqual(cfg['prediction_settings']['esmfold2-600-mlx']['chunk_size'],32)
if __name__=='__main__':unittest.main()
