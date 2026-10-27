"""Verify every completed receipt and export separate resident timing/memory arms."""
import argparse,csv,json,statistics
from pathlib import Path
from common import save,sha
from memory import summarize
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();out=a.output.resolve();cfg=json.loads((out/'manifest.json').read_text())
finished=json.loads((out/'finished.json').read_text());host=json.loads((out/'host_audit.json').read_text())
assert len(finished['results'])==len(cfg['blocks'])
primary={'smt3':'core','t4_lysozyme':'global','mbp':'global','citrate_synthase':'assembly_common_resolved'}
rows=[];summaries=[];verified_files=0;failures=[]
for block in cfg['blocks']:
 base=out/'blocks'/block['id'];records=[]
 if not (base/'completed.json').exists():
  failures.append(json.loads((base/'terminal_failure.json').read_text()));continue
 complete=json.loads((base/'completed.json').read_text());load=json.loads((Path(complete['session'])/'load.json').read_text())
 assert '/agent/runtime_views/' in load['runtime_view'] or '/runtime_view' in load['runtime_view']
 for name in complete['outputs']:
  path=Path(name);m=json.loads(path.read_text());receipt=json.loads(path.with_name('complete.json').read_text())
  assert all(sha(p)==h for p,h in receipt['files'].items()),path
  verified_files+=len(receipt['files'])
  assert m['pid']==load['pid'] and m['model_identity']==load['model_identity'] and m['model_load_count']==1
  assert not m['geometry']['errors']
  peaks=m['memory']['peaks'];assert m['memory']['samples']>0
  row=dict(target=block['target'],arm=block['name'],residues=cfg['targets'][block['target']]['length'],seed=m['seed'],warmup=m['warmup'],request_seconds=m['request_seconds'],model_seconds=m['stages']['model_total']['seconds'],cpu_seconds=m['cpu_seconds'],footprint_gib=peaks['tree_footprint_bytes']/2**30,rss_gib=peaks['tree_rss_bytes']/2**30,mlx_peak_gib=m['allocator']['mlx_peak_bytes']/2**30,mlx_cache_gib=m['allocator']['mlx_cache_bytes']/2**30,system_swap_gib=peaks['swap_used_bytes']/2**30,ca_rmsd=m['crystal'][primary[block['target']]]['ca_rmsd'],ca_lddt=m['crystal'][primary[block['target']]]['ca_lddt'],plddt=m['scores']['complex_plddt'],ptm=m['scores']['ptm'],load_seconds=load['load_seconds'],load_footprint_gib=load['memory']['peaks']['tree_footprint_bytes']/2**30,chunk_size=block['chunk_size'],cache_limit_mib=block['cache_limit_mib'],pid=m['pid'],model_identity=m['model_identity'],timing_qualified=host['timing_qualified'])
  row.update(domain_N_ca_rmsd=m['crystal'].get('domain_N',{}).get('ca_rmsd'),domain_C_ca_rmsd=m['crystal'].get('domain_C',{}).get('ca_rmsd'),interface_contact_precision=m['crystal'].get('interface_ca_contacts_8A',{}).get('precision'),interface_contact_recall=m['crystal'].get('interface_ca_contacts_8A',{}).get('recall'),iptm=m['scores'].get('iptm'),ipsae_min=m['scores'].get('ipsae_min'),geometry_violations=len(m['geometry']['violations']),memory_samples=m['memory']['samples'])
  rows.append(row)
  if not m['warmup']:records.append(row)
 assert sorted(r['seed'] for r in records)==cfg['protocol']['seeds']
 session_memory=summarize(Path(complete['session'])/'memory.jsonl')
 summary=dict(target=block['target'],arm=block['name'],n=len(records),residues=records[0]['residues'],cold_load_seconds=load['load_seconds'],initialization_footprint_gib=records[0]['load_footprint_gib'],whole_session_footprint_peak_gib=session_memory['peaks']['tree_footprint_bytes']/2**30,whole_session_rss_peak_gib=session_memory['peaks']['tree_rss_bytes']/2**30)
 for metric in ('request_seconds','model_seconds','footprint_gib','rss_gib','mlx_peak_gib','ca_rmsd','ca_lddt','plddt','ptm'):
  values=[r[metric] for r in records];summary[metric]=dict(mean=statistics.mean(values),sd=statistics.stdev(values),minimum=min(values),maximum=max(values))
 summaries.append(summary)
paired=[]
for target in cfg['targets']:
 for seed in cfg['protocol']['seeds']:
  paths=[]
  for arm in ('figure2a','low_memory'):
   unit=out/'blocks'/(target+'_'+arm)/('seed_'+str(seed))
   if (unit/'measurement.json').is_file():paths.append(Path(json.loads((unit/'measurement.json').read_text())['structure']))
  if len(paths)==2:paired.append(dict(target=target,seed=seed,structure_byte_identical=paths[0].read_bytes()==paths[1].read_bytes()))
analysis=out/'analysis';analysis.mkdir(exist_ok=True)
with (analysis/'measurements.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
result=dict(complete=not failures,measured_predictions=sum(not r['warmup'] for r in rows),warmups=sum(r['warmup'] for r in rows),verified_files=verified_files,host_audit=host,failures=failures,paired_structure_checks=paired,summaries=summaries,protocol=cfg['protocol'],limitations=['Resident seeds, not independent cold starts','Measured on a 64 GB M4 Max; no 16 GB hardware validation','Footprint is accounted process-tree memory; not exact physical RAM','MLX allocator and process measurements are separate, not additive','Low-memory arm changes cache and chunking together','Sequence-only model; no matched-MSA claim against Full','Training-era crystal agreement is not blind accuracy or binding efficacy'])
result['analysis_script_sha256']=sha(__file__)
save(analysis/'summary.json',result)
lines=['# ESMFold2-600 Figure 2a benchmark','',f"Measured outputs: {result['measured_predictions']}; warmups: {result['warmups']}; receipt-listed files verified: {verified_files}.",f"Host timing qualified: {host['timing_qualified']}.",'','| Target | Arm | n | Request s, mean ± SD | Accounted footprint GiB, mean ± SD | Whole-session footprint peak GiB | MLX peak GiB, mean | CA RMSD Å, mean |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for s in summaries:
 t=s['request_seconds'];m=s['footprint_gib'];lines.append(f"| {s['target']} | {s['arm']} | {s['n']} | {t['mean']:.3f} ± {t['sd']:.3f} | {m['mean']:.3f} ± {m['sd']:.3f} | {s['whole_session_footprint_peak_gib']:.3f} | {s['mlx_peak_gib']['mean']:.3f} | {s['ca_rmsd']['mean']:.3f} |")
lines+=['','Cold-load, warmup, model-stage, RSS, CPU, confidence and per-seed data are retained separately in measurements.csv and summary.json.','']+['- '+x for x in result['limitations']]
(analysis/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('summaries','protocol')},indent=2))
