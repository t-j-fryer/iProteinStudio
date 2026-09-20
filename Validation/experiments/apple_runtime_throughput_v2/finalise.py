"""Final CPU audit; requires a separately recorded terminal broker inventory."""
import json
from collections import Counter
from pathlib import Path
from analyse import analyse,extract,compare,POLICY
from worker import atomic
from prepare import SPECS,ROOT,OUT
HERE=Path(__file__).resolve().parent

def main():
 statuses=json.loads((OUT/'terminal_status.json').read_text())
 assert len(statuses)==len(list(OUT.glob('*/submitted.json')))
 assert all(r['status'] in ('completed','failed','cancelled') for r in statuses)
 blocks=set();units=set();audits=[]
 for row in statuses:
  if row['status']!='completed':continue
  run=OUT/row['run'];a=analyse(run);assert not a['errors'],a['errors'];audits.append(a)
  for value in json.loads((run/'progress.json').read_text()).values():
   block=Path(value);blocks.add(str(block));units.update(json.loads((block/'result.json').read_text())['rows'])
 installed={}
 expected={'intellifold':'2.6.0','protenix':'2.7.1','constraint':'2.7.1','openfold':'2.6.0','nesso':'2.11.0','antifold':'2.2.0','rfd3':'2.13.0'}
 for engine,(rel,py,_) in SPECS.items():
  site=ROOT/rel/f'lib/python{py}/site-packages';versions={}
  for package in ('torch','mlx'):
   found=list(site.glob(package+'-*.dist-info'))
   if found:versions[package]=found[0].name.removeprefix(package+'-').removesuffix('.dist-info')
  assert versions['torch']==expected[engine],(engine,versions)
  installed[engine]=versions
 assert installed['rfd3']['mlx']=='0.32.0'
 limits=json.loads((HERE/'manifest.json').read_text())['acceptance'];reproduction=[]
 for engine in ('protenix','constraint'):
  smoke=next(OUT.glob(engine+'_smoke_*'));tape=next(OUT.glob(engine+'_tape_*'))
  for i in (0,1):
   a=extract(smoke/'baseline/attempt_001'/f'unit_{i+1:02d}',engine);b=extract(tape/'baseline/attempt_001'/f'unit_{i:02d}',engine)
   reproduction.append(dict(engine=engine,**compare(a,b,engine,limits)))
 atomic(OUT/'baseline_capture_reproducibility.json',dict(scope='Same installed runtime and seed: original replay versus RNG capture. Diagnostic only.',analysis_policy=POLICY,rows=reproduction))
 counts=Counter()
 for path in units:
  row=json.loads(Path(path).read_text());counts['warmup' if row['warmup'] else 'profiled' if row['profiled'] else 'measured_or_replay']+=1
 result=dict(status='bounded screen complete; no production settings promoted',job_counts=dict(Counter(r['status'] for r in statuses)),unique_completed_blocks=len(blocks),unique_completed_output_units=len(units),units_by_role=dict(counts),completed_output_audit_errors=0,installed_versions=installed,analysis_policy=POLICY,paired_comparisons=sum(bool(a['pairs']) for a in audits),paired_gate_passes=sum(a['passed'] for a in audits),limitations=['No full campaign/restart/soak promotion validation','Only this M4 Max and small computational fixtures','SUMO core unavailable for low-confidence Protenix/OpenFold fixtures','No antibody-specific AntiFold holdout','No installed app or engine default changes'])
 atomic(OUT/'FINAL_AUDIT.json',result);print(json.dumps(result,indent=2))
 def timing(pattern):
  files=sorted(OUT.glob(pattern+'/analysis.json'))
  d=json.loads(files[-1].read_text());pairs=[p for p in d['pairs'] if not p['warmup']]
  a=sum(p['baseline_seconds'] for p in pairs);b=sum(p['candidate_seconds'] for p in pairs)
  return f'{a:.3f} → {b:.3f} s ({100*(b/a-1):+.1f}%)'
 notes=['## Decisions from this screen','',
 'All 48 submitted plans are terminal: 38 completed, 8 retained failures, 2 cancelled before inference. No app defaults or installed runtimes were changed. These are short computational fixtures, not validated binder-design throughput.','',
 '| Engine / change | Measured result | Interpretation |','|---|---|---|',
 '| IntelliFold Flash / padding | '+timing('intellifold-flash_buckets_*')+' | Contemporaneous screen passes; saved coordinates/confidence identical. Applies only when total input fits 128 tokens. |',
 '| IntelliFold Full / padding | '+timing('intellifold-full_buckets_*')+' | Passes, but earlier control: exact gain is provisional. Same ≤128-token limitation. |',
 '| NESSO / CCD cache, Torch 2.11 | '+timing('nesso_ccd_20260919T2218*')+' | Passes against earlier control; the separate 2.14 contemporaneous cache pair also passes. Prefer caching over upgrading NESSO. |',
 '| OpenFold / initialization | '+timing('openfold_init_20260919T2242*')+' | All final parameters verified against checkpoint; checked outputs retained. Earlier timing control and unavailable SUMO core limit qualification. |',
 '| OpenFold / SDPA | '+timing('openfold_attention_20260919T2242*')+' | Other gates pass; SUMO core unavailable. Small difference against earlier control does not establish a gain. |',
 '| RFD3 / native SDPA confirmation | '+timing('rfd3_attention_20260919T2239*')+' | Numerical gates pass; fresh reversed-order pair is slower. Reject initial apparent speed gain. |',
 '| RFD3 / custom Metal | See operator and trajectory tables | Faster operator; one complete trajectory exceeds coordinate tolerance. Rounding-preserving alternative fails its MLX-equivalence oracle. Keep existing implementation. |',
 '| Protenix Full / invariant cache | '+timing('protenix_cache_*')+' | Other gates pass; SUMO core unavailable. Small earlier-control difference needs larger-fixture confirmation. |',
 '| Protenix Constraint / invariant cache | '+timing('constraint_cache_*')+' | Numerical pass; small earlier-control difference is not an established speed gain. |','',
 'PyTorch 2.14 is promising for IntelliFold Flash (18–55% less time in two process pairs; matched-draw arithmetic replay passes). Full IntelliFold has only a small single-pair runtime gain. NESSO is 19–25% slower in two pairs. Protenix Full/Constraint remain structurally different after recorded Torch-draw replay; OpenFold also fails the runtime-equivalence screen. AntiFold passes and is about 9% faster after both shapes are warmed, but its absolute cost is already small. No blanket runtime upgrade is justified.','',
 'The 128-token padding result does not apply to a target–binder complex whose combined token count exceeds 128. Larger complexes, interfaces, MSA-rich inputs, combined optimizations, campaign restart/cancellation and memory soaks remain future validation. A passing numerical screen establishes agreement within declared limits, not experimental protein accuracy.','',
 'Final receipts and output counts: [FINAL_AUDIT.json](FINAL_AUDIT.json). Runtime and implementation figures: [OVERVIEW.svg](OVERVIEW.svg), [IMPLEMENTATIONS.svg](IMPLEMENTATIONS.svg).','']
 (OUT/'DECISIONS.md').write_text('\n'.join(notes))
if __name__=='__main__':main()
