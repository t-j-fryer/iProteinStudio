"""MCP/CLI result views retain saved search gates and do not infer validation."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1]
PIPE=REPO/'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0]=[str(PIPE/'mcp'),str(PIPE/'scripts')]
from iprotein_mcp.catalog import results_overview,query_results
from rfd4.contract import seal

class SavedGateTests(unittest.TestCase):
 def test_scoped_saved_verdict_is_identical_in_overview_and_query(self):
  with tempfile.TemporaryDirectory() as raw,patch.dict(os.environ,NANOHUNTER_ROOT=raw):
   root=Path(raw)/'projects/test/rfd4_runs/fixture';root.mkdir(parents=True)
   (root/'rfd4_config.json').write_text(json.dumps(dict(settings=dict(binder_chain='A'))))
   (root/'results.json').write_text('[]')
   for name,verdict in [('pass',True),('fail',False),('unfiltered',None)]:
    leaf=root/'candidates'/name;leaf.mkdir(parents=True);pdb=leaf/'model.pdb';pdb.write_text('fixture')
    row=dict(id=name,family=name,structure=str(pdb),sequence='AAAA',ipsae_min=.9)
    if verdict is not None:row.update(hit_filter_passed=verdict,hit_filter_cutoffs={'ipsae_min':.5},hit_filter_failures=[] if verdict else ['iptm'],hit_filter_scope='design_feedback_not_independent_validation')
    seal(leaf/'completed.json',row,[pdb])
   run='test/rfd4_runs/fixture'
   overview=results_overview(run,limit=20,hit_only=False)
   groups={g['id']:g for g in overview['groups']}
   self.assertTrue(groups['pass']['is_hit']);self.assertFalse(groups['fail']['is_hit']);self.assertIsNone(groups['unfiltered']['is_hit'])
   self.assertEqual(groups['pass']['variants'][0]['artifacts'][0]['hit_filter_scope'],'design_feedback_not_independent_validation')
   self.assertEqual([g['id'] for g in results_overview(run,limit=20,hit_only=True)['groups']],['pass'])
   self.assertEqual([r['id'] for r in query_results(run,'results.json',None,True,20)['rows']],['pass'])
   # A complete assembly exports its atom map and geometry report with the design.
   leaf=root/'candidates/pass';structure=leaf/'model.pdb';mapping=leaf/'model.atom_map.json';mapping.write_text('{}')
   audit=leaf/'assembly_audit.json';audit.write_text('{"passed": true}')
   confidence=leaf/'confidence.json';confidence.write_text('{"ipsae_min": 0.9}')
   row=dict(id='pass',family='pass',structure=str(structure),sequence='AAAA',ipsae_min=.9,hit_filter_passed=True,assembly_audit={'passed':True},confidence=str(confidence))
   seal(leaf/'completed.json',row,[structure,mapping,audit,confidence])
   artifacts=results_overview(run,limit=20,hit_only=True)['groups'][0]['variants'][0]['artifacts']
   self.assertEqual({a['role'] for a in artifacts},{'design','ligand_atom_mapping','complete_assembly_audit'})
   self.assertFalse(Path(artifacts[0]['confidence_json']).is_absolute())
   pdb.write_text('tampered')
   with self.assertRaises(ValueError):results_overview(run,limit=20,hit_only=False)

if __name__=='__main__':unittest.main()
