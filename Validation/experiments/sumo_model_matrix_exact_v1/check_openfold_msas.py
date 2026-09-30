"""CPU-only native parser regression against the exact campaign alignments."""
import json,subprocess,sys,tempfile
from pathlib import Path
from common import sha,save
from openfold3.core.data.io.sequence.msa import parse_msas_direct
from openfold3.projects.of3_all_atom.config.dataset_config_components import MSASettings

repo=Path(__file__).resolve().parents[3]
out=repo/'Validation/output/sumo_model_matrix_exact_v1'
cfg=json.loads((out/'frozen/config.json').read_text())
helper=repo/'Sources/iProteinStudio/Resources/pipeline/scripts/openfold_query_json.py'
counts=MSASettings().max_seq_counts
rows=[]
with tempfile.TemporaryDirectory(prefix='openfold-msa-check-') as tmp:
 for arm,expected in [('128',128),('full',8060)]:
  unit=Path(tmp)/arm;unit.mkdir();source=Path(cfg['msas'][arm])
  assert parse_msas_direct([source],counts)=={},'Expected reproduction of filename filtering'
  inp=unit/'input.yaml';query=unit/'query.json'
  inp.write_text('version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: '+cfg['sequence']+'\n      msa: '+str(source)+'\n')
  subprocess.run([sys.executable,str(helper),str(inp),cfg['sequence'],'sumo',str(query),'','','42'],check=True)
  q=json.loads(query.read_text())['queries']['sumo'];assert q['use_msas'] and q['use_main_msas'] and not q['use_paired_msas']
  staged=Path(q['chains'][0]['main_msa_file_paths'][0]);assert sha(staged)==sha(source)==cfg['msa_hashes'][arm]
  parsed=parse_msas_direct([staged],counts)['colabfold_main']
  assert parsed.msa.shape==(expected,len(cfg['sequence'])),parsed.msa.shape
  assert ''.join(parsed.msa[0])==cfg['sequence']
  rows.append(dict(arm=arm,shape=list(parsed.msa.shape),sha256=sha(staged),helper_sha256=sha(helper),original_filename_reproduces_empty_parse=True))
save(out/'openfold_msa_parser_check.json',rows)
print(json.dumps(rows,indent=2))
