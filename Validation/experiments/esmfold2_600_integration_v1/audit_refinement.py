"""Audit completed 600M sequence-search proposals, frozen targets and receipts."""
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
repo=Path(__file__).resolve().parents[3];sys.path[:0]=[str(repo/'Sources/iProteinStudio/Resources/pipeline/scripts'),str(repo/'Sources/iProteinStudio/Resources/rfd3')]
from rfd4.contract import verify
from rfd4.search_engine import sequences
plan=json.loads(a.plan.read_text());root=Path(plan['normalized_request']['output']);verify(root/'search_completed.json')
cfg=json.loads((root/'rfd4_config.json').read_text());rows=json.loads((root/'results.json').read_text());assert len(rows)==6,len(rows)
for row in rows:
 conf=json.loads(Path(row['confidence']).read_text());assert conf['engine']==row['engine']=='esmfold2-600-mlx'
 assert conf['ipsae_min']==row['ipsae_min'];assert sequences(row['structure'])==row['sequences']
 assert row['sequence']==row['sequences']['A'];assert row['sequences']['B']==cfg['target_sequences']['B']
 assert conf['folding_revision']=='38fa0be7397a485afd4a752202447693098f3d50'
 for k in ('ptm','iptm','complex_plddt'):assert 0<=conf[k]<=1
assert len(set(row['sequence'] for row in rows))>1
result=dict(passed=True,plan_id=plan['id'],plan_sha256=plan['sha256'],code_snapshot=plan['code_snapshot']['sha256'],predictions=len(rows),cycles=2,beam_width=2,proposals_per_parent=2,engine='esmfold2-600-mlx',sequence_model='solublempnn',target_preserved=True,metrics=[dict(id=r['id'],cycle=r['cycle'],ipsae_min=r['ipsae_min']) for r in rows])
a.output.write_text(json.dumps(result,indent=2)+'\n');print('Audited six 600M beam proposals across two MPNN/refold cycles; target preserved.')
