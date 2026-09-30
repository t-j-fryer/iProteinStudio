"""Freeze table and validated target alignments; never edits supplied research data."""
import csv,hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
SOURCE=Path('/Users/thomasfryer/Coding/AI_DBTL_PAPER/Screening')
TABLE=SOURCE/'Nanopore_Consensus_Reanalysis/Integrated_Analysis/In_Silico_Filtering/data/paper_design_master_table.csv'
OUT=REPO/'Validation/output/paper_binder_matrix_v1'
OUT.mkdir(exist_ok=False);inputs=OUT/'inputs';inputs.mkdir()
shutil.copy2(TABLE,inputs/'paper_design_master_table.csv')
cfg=json.loads((REPO/'Validation/output/sumo_model_matrix_exact_v1/frozen/config.json').read_text())
SUMO=cfg['sequence'];rows=list(csv.DictReader(TABLE.open()));targets={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def records(text):return [r.strip() for r in text.split('>') if r.strip()]
def query(record):return ''.join(c for c in ''.join(record.splitlines()[1:]) if c.isupper())
for row in rows:
 seq=SUMO if row['target']=='SUMO' else row['target_amino_acid_sequence']
 key=hashlib.sha256(seq.encode()).hexdigest()[:12]
 targets.setdefault(key,dict(sequence=seq,labels=[],key=key))
 if row['target'] not in targets[key]['labels']:targets[key]['labels'].append(row['target'])
 row['target_key']=key
 row['effective_target_sequence']=seq
 row['binder_sequence']=row['binder_amino_acid_sequence']
 assert row['binder_sequence'] and not set(row['binder_sequence'])-set('ACDEFGHIKLMNPQRSTVWY')
for t in targets.values():
 folder=inputs/t['key'];folder.mkdir()
 if t['sequence']==SUMO:
  original=Path(cfg['msas']['full']);selected=Path(cfg['msas']['128'])
  shutil.copy2(original,folder/'full.a3m');shutil.copy2(selected,folder/'128.a3m')
  t['source']=str(original)
for path in (SOURCE/'AF3_structures/predictions').glob('*/*data.json'):
 if all('source' in t for t in targets.values()):break
 data=json.loads(path.read_text())
 for entry in data['sequences']:
  protein=entry.get('protein',{});seq=protein.get('sequence','')
  key=hashlib.sha256(seq.encode()).hexdigest()[:12]
  if key not in targets or 'source' in targets[key]:continue
  text=protein.get('unpairedMsa','');recs=records(text)
  if not recs:continue
  assert query(recs[0])==seq,(path,seq)
  assert all(len(''.join(c for c in ''.join(r.splitlines()[1:]) if not c.islower() and c!='.'))==len(seq) for r in recs)
  folder=inputs/key;(folder/'full.a3m').write_text(text)
  (folder/'128.a3m').write_text('>'+ '\n>'.join(recs[:128])+'\n')
  targets[key]['source']=str(path);targets[key]['source_sha256']=sha(path)
for t in targets.values():
 assert 'source' in t,('MISSING_ALIGNMENT',t)
 folder=inputs/t['key'];t['msa']=str(folder/'128.a3m');t['msa_sha256']=sha(t['msa'])
 recs=records(Path(t['msa']).read_text());t['rows']=len(recs);t['distinct_aligned_sequences']=len({''.join(r.splitlines()[1:]) for r in recs})
 t['query_only']=t['distinct_aligned_sequences']==1
 assert query(recs[0])==t['sequence'] and len(recs)<=128
cfg['engines'].pop('intellifold_full');cfg['output']=str(OUT)
cfg.update(rows=rows,targets=targets,source_table=str(TABLE),source_table_sha256=sha(TABLE),seeds=[42],
 protocol='Binder A explicitly empty MSA; target B supplied MSA capped128; SUMO replaced by benchmark96 sequence; Fast all empty MSA/full50steps; other engines reduced steps from exact matrix. One sample per seed. No restraints/templates. Boltz potentials off as benchmark.',
 assumptions=['Main binder_amino_acid_sequence column (identical to designed column); 33 nonempty assayed variants differ and are not substituted.', 'One CSV Myc label has a TrxA108 sequence/design ID; sequence retained and label discrepancy recorded.', 'ALFA/Myc saved AF3 MSAs contain duplicate query rows only, explicitly labelled query-only rather than claiming homolog support.'])
(OUT/'inventory.json').write_text(json.dumps(cfg,indent=2)+'\n')
print(json.dumps(dict(rows=len(rows),targets=[{k:t[k] for k in ('key','labels','rows','distinct_aligned_sequences','query_only')} for t in targets.values()]),indent=2))
