"""Rebuild derived report/figure from immutable measured blocks and audited pairs."""
import csv,json
from pathlib import Path
import numpy as np
from worker import atomic
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/apple_runtime_throughput_v2'
LABELS={'intellifold-flash':'IntelliFold Flash','intellifold-full':'IntelliFold Full','protenix':'Protenix Full','constraint':'Protenix Constraint','nesso':'NESSO','openfold':'OpenFold3','rfd3':'RFD3 (MLX)','antifold':'AntiFold'}
def core_only(a):
 return not a['errors'] and {f for p in a['pairs'] for f in p['failures']}=={'insufficient high-confidence SUMO core'}
def screen_times(r):
 pairs=[p for p in r['analysis']['pairs'] if not p['warmup']]
 divisor=len(pairs)/2 if r['stage']=='steady' else 1
 return sum(p['baseline_seconds'] for p in pairs)/divisor,sum(p['candidate_seconds'] for p in pairs)/divisor
def main():
 runs=[];measured=[];profiles=[];setups=[]
 for p in sorted(OUT.glob('*_20*/frozen/run.json')):
  cfg=json.loads(p.read_text());run=p.parent.parent;stage=run.name.split('_')[1];analysis=json.loads((run/'analysis.json').read_text()) if (run/'analysis.json').exists() else None
  rows=[]
  for rp in sorted(run.glob('*/attempt_*/result.json')):
   result=json.loads(rp.read_text())
   if 'model_load_seconds' in result:setups.append(dict(run=run.name,engine=cfg['blocks'][0]['engine'],stage=stage,arm=rp.parents[1].name,setup_seconds=result['model_load_seconds'],process_seconds=result['process_seconds']))
  for mp in sorted(run.glob('*/attempt_*/unit_*/measurement.json')):
   r=json.loads(mp.read_text());arm=mp.parents[2].name;record=dict(run=run.name,engine=cfg['blocks'][0]['engine'],stage=stage,arm=arm,case=r['name'],warmup=r['warmup'],profiled=r['profiled'],seconds=r['seconds'],cpu_seconds=r['cpu_seconds'],path=str(mp));rows.append(record);measured.append(record)
   if r['profiled']:profiles.append(dict(**record,stages=r['stages'],details=r['details']))
  runs.append(dict(run=run.name,engine=cfg['blocks'][0]['engine'],stage=stage,complete=(run/'completed.json').exists(),analysis=analysis,rows=rows,blocks=cfg['blocks'],reused_reference=cfg.get('reused_reference'),failures=json.loads((run/'failures.json').read_text()) if (run/'failures.json').exists() else []))
 atomic(OUT/'measurements.json',dict(runs=runs,profiles=profiles,setups=setups))
 if measured:
  with (OUT/'timings.csv').open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(measured[0]));w.writeheader();w.writerows(measured)
 lines=['# Other-engine Apple runtime screen','','M4 Max /64GB /macOS26.6.1. Isolated exploratory experiments; installed defaults unchanged.','',
 '[Anthropic report review and Apple kernel follow-up](../../../docs/APPLE_KERNEL_REVIEW.md).','',
 'Runtime comparisons fix checkpoints, scientific settings, seed, explicit empty MSA and outputs. One first-call warmup is excluded per process; the table sums the two measured inputs (ubiquitin76 + SUMO96). A first-seen input shape may still include graph compilation. The separate AntiFold steady test warms both shapes before four repetitions per shape. NESSO adds acetate. RFD3 generates unconditional backbones at those lengths. AntiFold measures logits on fixed monomer backbones. OpenFold timings include a model reload per input. These are small computational fixtures, not a binding benchmark or full campaign validation.','',
 '| Engine | Baseline two-input seconds | Candidate seconds | Time change | Numerical screen |','|---|---:|---:|---:|---|']
 screens={}
 for r in runs:
  if r['stage']=='smoke' and r['complete'] and r['analysis'] and r['analysis']['pairs']:screens[r['engine']]=r
  if r['engine']=='antifold' and r['stage']=='steady' and r['complete'] and r['analysis'] and r['analysis']['pairs']:screens[r['engine']]=r
 for engine,r in screens.items():
  failed={p['name'] for p in r['analysis']['pairs'] if not p['passed']};replayed=set()
  for d in runs:
   if d['engine']==engine and d['stage']=='tape' and d['complete'] and d['analysis'] and d['analysis']['passed']:
    replayed.update(p['name'] for p in d['analysis']['pairs'])
  r['numerical_label']='Pass' if r['analysis']['passed'] else 'Core unavailable; other checks pass' if core_only(r['analysis']) else 'Matched-draw pass; RNG changed' if failed and failed.issubset(replayed) else 'Investigate / do not promote'
 for engine,label in LABELS.items():
  r=screens.get(engine)
  if not r:lines.append(f'| {label} | — | — | — | Not yet completed/audited |');continue
  a,b=screen_times(r)
  lines.append(f'| {label} | {a:.3f} | {b:.3f} | {100*(b/a-1):+.1f}% | {r["numerical_label"]} |')
 lines+=['','A matched-draw pass means the original whole-structure gate was repeated using identical recorded random inputs. Original same-seed failures remain visible below. Upgrading the RNG changes seed-to-output reproducibility; exact replay still requires the recorded runtime. The diagnostic’s transfer-instrumented timings are excluded from speed claims.']
 lines+=['','AntiFold’s headline uses its both-shapes-warmed confirmation: four repetitions per input shape, reported as the mean equivalent two-input time. Its initial shape-compilation-sensitive screen remains in the full table below.']
 lines+=['','SUMO analysis amendment requested by the user: align and score CA coordinates on baseline residues21 onward with pLDDT ≥80 (minimum20 selected residues), using those same indices in the candidate. The candidate cannot shrink the mask. Whole-chain coordinate differences remain diagnostic; whole-chain geometry and PAE/PDE checks remain. Prior audits are preserved as `analysis_original_whole_chain.json`, and every current audit records the versioned analysis-policy hash.']
 lines+=['','If the baseline lacks enough high-confidence SUMO residues, core equivalence is unassessable and cannot pass; there is no fallback to a whole-chain coordinate gate. This is a limitation of the fixture, not proof that the candidate runtime is inaccurate.']
 lines+=['','## All contrasts','','Time change uses the sum of measured outputs, excluding warmup (two per arm, except AntiFold steady: eight). Reused-reference screens are useful for rejecting implementations; their earlier control is not a contemporaneous speed comparison. RNG and random-tape diagnostics are not throughput measurements.','',
 '| Run | Completed | Output / equivalence audit | Measured seconds, control → candidate | Time change | Outputs recorded |','|---|---|---|---:|---:|---:|']
 for r in runs:
  a=r['analysis'];pairs=[p for p in a['pairs'] if not p['warmup']] if a else [];timing='—';change='—'
  audit='Pending'
  if a:
   audit=('Output audit error' if a['errors'] else ('Pass' if a['passed'] else 'Equivalence gate failed') if pairs else 'Outputs audited; unpaired')
   if pairs and core_only(a):audit='SUMO core unavailable; other gates pass'
  if pairs and r['stage'] not in ('rng','tape'):
   x=sum(p['baseline_seconds'] for p in pairs);y=sum(p['candidate_seconds'] for p in pairs)
   timing=f'{x:.3f} → {y:.3f}';change=f'{100*(y/x-1):+.1f}%'
   if r['reused_reference']:change+=' (earlier control)'
  lines.append(f'| [{r["run"]}]({r["run"]}/) | {r["complete"]} | {audit} | {timing} | {change} | {len(r["rows"])} |')
 lines+=['','## Startup outside timed inputs','','Worker setup includes engine imports and resident model loading where applicable; initial Torch import occurs before this timer. OpenFold reloads its model inside each timed prediction, so its row below only covers adapter setup. Process time includes setup, warmup and measured outputs, but excludes the coordinator’s runtime-seal verification.','',
 '| Engine / arm | Worker setup (s) | Whole worker process (s) |','|---|---:|---:|']
 for s in setups:
  if s['stage']=='smoke':lines.append(f'| {LABELS[s["engine"]]} / {s["arm"]} | {s["setup_seconds"]:.3f} | {s["process_seconds"]:.3f} |')
 lines+=['','## Stage profiles','','Synchronized diagnostics are separate from unprofiled timing comparisons. Nested model timings overlap: do not sum model_total with diffusion/confidence. Parent process CPU time omits preprocessing child CPU time and is not a CPU wall-time fraction.','']
 for p in profiles:lines.append(f'- {p["engine"]} / {p["case"]}: total {p["seconds"]:.3f}s; '+', '.join(f'{k}={v["seconds"]:.3f}s ({v["calls"]} calls)' for k,v in p['stages'].items()))
 for p in OUT.glob('rfd3_kernel_*/kernel/attempt_*/kernel_benchmark.json'):
  if not (p.parents[2]/'completed.json').exists():continue
  kernel=json.loads(p.read_text());lines+=['','## Sparse attention operator experiment','',kernel['scope'],'','| Shape L/K/H/d | Dtype | Eager ms | Compiled ms | SDPA ms | Custom Metal ms |','|---|---|---:|---:|---:|---:|']
  for row in kernel['rows']:
   t=row['median_seconds'];lines.append(f'| {row["shape"]} | {row["dtype"]} | '+ ' | '.join(f'{t[k]*1000:.4f}' for k in ('eager','compiled','sdpa','metal'))+' |')
  lines+=['','Independent-oracle results (thresholds unchanged):']
  for row in kernel['rows']:
   if 'oracle_passed' in row:
    lines.append(f'- {row["shape"]}, {row["dtype"]}: '+', '.join(f'{name}: relative L2={value:.6g} ({"pass" if row["oracle_passed"][name] else "FAIL"})' for name,value in row['oracle_relative_l2'].items()))
 diagnostic=OUT/'coordinate_diagnostics.json'
 if diagnostic.exists():
  d=json.loads(diagnostic.read_text());lines+=['','## Coordinate localization','',''+d['purpose'],'','| Model / input | All CA RMSD (Å) | Joint pLDDT ≥70 CA RMSD (Å) | Selected residues |','|---|---:|---:|---:|']
  for r in d['rows']:lines.append(f'| {r["run"].split("_smoke_")[0]} / {r["case"]} | {r["all_ca_rmsd"]:.3f} | {r["joint_plddt70_ca_rmsd"]:.3f} | {r["joint_plddt70_residues"]}/{r["total_residues"]} |')
 lines+=['','## Limits','','No production promotion, antibody-specific AntiFold holdout, interfaces or ipSAE rankings, deep MSAs, large complexes, full campaign restart/soak, release packaging, other chips or OS versions. Confidence agreement alone does not establish structural or experimental accuracy. Failed runtime coordinate gates require diagnosis; same seed need not mean the same random draws across framework versions. Package pin conflicts are retained in `*.dependencies.txt`. Raw incomplete and failed attempts remain on disk.','']
 (OUT/'REPORT.md').write_text('\n'.join(lines))
 if (OUT/'DECISIONS.md').exists():
  content=(OUT/'REPORT.md').read_text();lead,rest=content.split('\n',1)
  (OUT/'REPORT.md').write_text(lead+'\n\n'+(OUT/'DECISIONS.md').read_text()+rest)
 if screens:plot(screens,profiles)
 plot_implementations(runs)
def plot_implementations(runs):
 labels={'buckets':'128-token minimum padding','cache':'diffusion invariant cache','ccd':'CCD parse cache','esm':'ESM backbone outputs','attention':'native SDPA','init':'checkpoint initialization','metal':'custom Metal attention','metalround':'Metal with original BF16 rounding','threads':'1 vs 4 CPU threads'}
 selected=[r for r in runs if r['stage'] in labels and r['complete'] and r['analysis'] and r['analysis']['pairs']]
 if not selected:return
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'Arial','font.size':10,'svg.fonttype':'none'})
 fig,ax=plt.subplots(figsize=(12,max(4,2+.62*len(selected))))
 names=[];changes=[]
 for j,r in enumerate(selected):
  pairs=[p for p in r['analysis']['pairs'] if not p['warmup']];a=sum(p['baseline_seconds'] for p in pairs);b=sum(p['candidate_seconds'] for p in pairs);change=100*(b/a-1);changes.append(change)
  runtime='MLX '+('0.32.0' if r['blocks'][-1]['runtime']=='baseline' else '0.32.2') if r['engine']=='rfd3' else 'Torch '+r['blocks'][-1]['torch_version'];earlier=' *' if r['reused_reference'] else ''
  names.append(f'{LABELS[r["engine"]]} · {labels[r["stage"]]}\n{runtime}{earlier}')
  status='Pass' if r['analysis']['passed'] else 'Core unavailable' if core_only(r['analysis']) else 'Investigate'
  ax.plot(change,j,'D',markersize=7,color='#287449' if status=='Pass' else '#a57420' if status=='Core unavailable' else '#ae3933')
  ax.annotate(f'{a:.2f} → {b:.2f}s   ({change:+.1f}%) · {status}',(change,j),xytext=(10,0),textcoords='offset points',va='center',fontsize=9)
 ax.set_yticks(range(len(names)),names);ax.set_ylim(len(names)-.5,-.5);ax.axvline(0,color='black',lw=.7);ax.grid(False);ax.tick_params(direction='in');ax.spines[['top','right']].set_visible(False)
 ax.set_xlim(min(-5,min(changes)-10),max(changes)+105);ax.set_xlabel('Change in elapsed time (%) · negative is faster')
 fig.suptitle('Implementation experiments · M4 Max',x=.025,ha='left',fontsize=16)
 fig.text(.025,.02,'Two measured inputs per arm; warmup excluded. Pass refers to numerical checks, not a confirmed speedup.\n* Earlier control. Padding gains require ≤128 total input tokens. Core unavailable: insufficient high-confidence SUMO residues.\nUnchanged scientific settings; no production defaults promoted.',fontsize=9)
 fig.tight_layout(rect=(0,.12,1,.94));fig.savefig(OUT/'IMPLEMENTATIONS.svg',transparent=True);fig.savefig(OUT/'IMPLEMENTATIONS.png',dpi=160);plt.close(fig)
def plot(screens,profiles):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'Arial','font.size':10,'axes.edgecolor':'black','text.color':'black','axes.labelcolor':'black','xtick.color':'black','ytick.color':'black','svg.fonttype':'none'})
 fig,axes=plt.subplots(1,2,figsize=(12,max(5.5,2.5+len(screens)*.55)),gridspec_kw={'width_ratios':[1.15,1]})
 selected=[e for e in LABELS if e in screens];y=np.arange(len(selected))
 for j,e in enumerate(selected):
  r=screens[e];a,b=screen_times(r)
  axes[0].plot([a,b],[j,j],color='#777777',lw=1)
  axes[0].plot(a,j,'o',color='#668db4',markeredgecolor='black',label='Installed runtime' if j==0 else None)
  axes[0].plot(b,j,'D',color='#e8ad74',markeredgecolor='black',label='Candidate runtime' if j==0 else None)
  fa=f'{a:.3f}' if a<1 else f'{a:.1f}';fb=f'{b:.3f}' if b<1 else f'{b:.1f}'
  axes[0].annotate(f'{fa}s',(a,j),xytext=(0,10),textcoords='offset points',ha='center',fontsize=8)
  axes[0].annotate(f'{fb}s',(b,j),xytext=(0,-16),textcoords='offset points',ha='center',fontsize=8)
  passed=r['numerical_label'] in ('Pass','Matched-draw pass; RNG changed');unavailable=core_only(r['analysis'])
  axes[1].plot(100*(b/a-1),j,'D',color='#287449' if passed else '#a57420' if unavailable else '#ae3933',markersize=7)
  label='Pass' if r['analysis']['passed'] else 'Matched-draw pass' if passed else 'Core unavailable' if unavailable else 'Numerical investigation'
  axes[1].annotate(label,(100*(b/a-1),j),xytext=(8,0),textcoords='offset points',va='center',fontsize=9)
 axes[0].set_yticks(y,[LABELS[e] for e in selected]);axes[0].invert_yaxis();axes[0].set_xscale('log');axes[0].set_xlabel('Seconds for the two measured inputs (log scale)');axes[0].legend(frameon=False,loc='best');axes[0].set_title('Fixed-input runtime screen',loc='left')
 axes[1].set_yticks(y,[]);axes[1].invert_yaxis();axes[1].axvline(0,color='black',lw=.7);axes[1].set_xlabel('Change in elapsed time (%)   •   negative is faster');axes[1].set_title('Speed change and numerical gate',loc='left');axes[1].margins(x=.7)
 for ax in axes:ax.set_ylim(len(selected)-.5,-.5);ax.tick_params(direction='in');ax.spines[['top','right']].set_visible(False);ax.grid(False)
 fig.suptitle('Apple runtime comparisons • M4 Max',x=.03,ha='left',fontsize=16)
 fig.text(.03,.025,'Exploratory process pairs; 2 measured inputs per arm. AntiFold: 4 warm repetitions/shape, mean equivalent two-input time.\nRFD3: MLX 0.32.0 → 0.32.2. Others: PyTorch 2.14. OpenFold includes reloads. No defaults promoted.',fontsize=9)
 fig.tight_layout(rect=(0,.10,1,.94));fig.savefig(OUT/'OVERVIEW.svg',transparent=True);fig.savefig(OUT/'OVERVIEW.png',dpi=160);plt.close(fig)
if __name__=='__main__':main()
