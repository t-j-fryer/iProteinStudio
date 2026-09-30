"""Build the interpretive report from audited measurements, preserving all controls."""
import json, statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE.parents[1]/'output/sumo_request_overhead_v1_retry01'
d=json.loads((OUT/'analysis/results.json').read_text())
b=json.loads((OUT/'analysis/batch_results.json').read_text())
normal=[r for r in d['rows'] if not r['diagnostic'] and not r['first_model_request']]
lookup={(s['engine'],s['variant']):s for s in d['summaries']}
lines=['# Resident request overhead: SUMO benchmark', '',
 'Measured on Apple M4 Max (40 GPU cores), 64 GB, macOS 26.6.1. SUMO96 monomer, the same cached 128-row MSA, 25 diffusion steps, unchanged native recycles, one sample, exact token lengths. Each condition has five warm requests, seeds 42–46; model loading and the first warmup are reported separately. Crystal comparison uses 3QHT chain A and SUMO residues 21–96, excluding the flexible N-terminus.', '',
 '## Findings', '',
 'The largest opportunities are repeated orchestration and reusable chemistry data. Protenix already caches its CCD/component data; ESMFold retains its input builder and directly calls a resident model. These provide useful implementation patterns, although each engine needs its own scientific validation.', '',
 '|Engine / intervention|Control median (s)|Optimized median (s)|Less request time|Saved outputs|',
 '|---|---:|---:|---:|---|']
comparisons=[('openfold3','baseline','w0_keep','Zero loader workers + MPS residency'),('openfold3','w0_keep','w0_keep_features_keyed','Additionally reuse identical-input features'),('boltz','baseline','keep','Keep model on MPS'),('boltz','keep','keep_prepared','Additionally cache parsed identical input'),('intellifold_flash','baseline','ccd','Cache CCD chemistry dictionary'),('intellifold_full','baseline_interleaved','ccd_interleaved','Cache CCD; alternating paired control')]
for engine,control,variant,label in comparisons:
 if (engine,control) not in lookup or (engine,variant) not in lookup:continue
 a=lookup[engine,control];z=lookup[engine,variant]
 fidelity='Identical coordinates and compared confidence arrays' if z['all_coordinate_exact'] and z['all_confidence_exact'] else 'Tiny floating-point differences; see paired numerical audit'
 lines.append(f"|{engine}: {label}|{a['request_seconds']:.3f}|{z['request_seconds']:.3f}|{100*(1-z['request_seconds']/a['request_seconds']):.1f}%|{fidelity}|")
lines+=['',
 'OpenFold: one or two loader workers did not materially help relative to ten. Zero workers removed most spawn/input-wait/shutdown overhead. The resident-MPS change removes repeated device transfers while retaining other trainer cleanup. The full feature cache applies only to an identical protein/MSA under this experiment’s fixed native feature RNG; changing binder sequences require new features. The first cache attempt recorded zero hits because request names were included in its key. That failed optimization is preserved below; the corrected key excludes only the output name.', '',
 'The generic OpenFold RDKit-coordinate conversion through NumPy did not establish a material additional gain: the conversion cost moved between libraries. It is not recommended on this evidence. Flash parsed-input caching also adds little after the CCD dictionary is retained.', '',
 'IntelliFold Full had substantial inference-time variation across sequential runs. The first uncached control, cached arm and repeated uncached control are all retained. Their total-time difference cannot be attributed entirely to caching. The final control alternates caching on/off within the same resident process for each seed, reversing order on odd seeds. No change was made to diffusion steps, recycles, precision, weights or inference math.', '',
 '## All normal request conditions', '',
 '|Engine|Condition|n|Request median s|Model median s|Outside-model median s|Core RMSD Å|Core CA-lDDT|',
 '|---|---|---:|---:|---:|---:|---:|---:|']
for s in d['summaries']:
 lines.append(f"|{s['engine']}|{s['variant']}|{s['n']}|{s['request_seconds']:.3f}|{s['model_seconds']:.3f}|{s['outside_seconds']:.3f}|{s['crystal_core_rmsd']:.5f}|{s['core_lddt']:.6f}|")
lines+=['', 'Each median is calculated independently; median request minus median model need not equal median outside-model time. Resident request includes native preparation, inference, writing and native validation; benchmark input staging and the independent post-request audit are outside that timer, consistently with the original matrix.', '', '## Alternating IntelliFold Full control', '', '|Seed|Uncached request s|Cached request s|Request saving s|Outside-model saving s|', '|---|---:|---:|---:|---:|']
diff=[];outside=[]
for seed in range(42,47):
 pair={r['variant']:r for r in normal if r['engine']=='intellifold_full' and r['seed']==seed and 'interleaved' in r['variant']}
 if len(pair)!=2:continue
 a=pair['baseline_interleaved'];z=pair['ccd_interleaved'];diff.append(a['request_seconds']-z['request_seconds']);outside.append(a['outside_seconds']-z['outside_seconds'])
 lines.append(f"|{seed}|{a['request_seconds']:.3f}|{z['request_seconds']:.3f}|{diff[-1]:.3f}|{outside[-1]:.3f}|")
if diff:lines+=['',f'Median within-seed request saving: {statistics.median(diff):.3f} s; median outside-model saving: {statistics.median(outside):.3f} s. These are paired differences, not differences of medians.']
lines+=['', '## Bounded directory prefetch', '', 'One five-seed directory-style request was measured per variant, after warmup. These are amortized batch timings, not five independent request medians.']
for row in b['rows']:lines.append(f"- {row['variant']}: {row['total_seconds']:.3f} s total / 5 = {row['amortized_seconds']:.3f} s per prediction.")
lines+=['', 'Two workers with prefetch factor one were slower than zero workers in this short workload. Larger inputs/queues and a persistent producer thread are untested; this does not rule out overlap gains in those regimes.', '', '## Fidelity and completeness', '', f"Audited {len(normal)} normal separate requests, {len(d['rows'])-len(normal)} warmup/diagnostic requests, and {sum(len(x['pairs']) for x in b['rows'])} batch predictions. Separate-request audit errors: {len(d['audit_errors'])}; batch audit errors: {len(b['errors'])}.", '',
 'Audits check requested sequence/atom identities, finite coordinates/confidence, required confidence files, geometry, same-seed coordinates and confidence arrays, and crystal-core RMSD/CA-lDDT. Exact means equality of saved coordinate arrays and compared confidence fields, not byte-identical metadata. The practical numerical screen is core difference ≤0.01 Å, no extra geometry violations, pTM/confidence-score difference ≤0.0001, normalized pLDDT difference ≤0.001, PAE/PDE difference ≤0.01 Å. This screen was specified after seeing small float differences; it was not preregistered.', '',
 f"All completed five-seed non-control conditions pass the numerical screen: {all(s['numerical_screen_pass'] for s in d['summaries'] if s['paired_n']==5)}. Normal structures flagged by geometry checks: {sum(r['geometry_violations']>0 for r in normal)}.", '',
 '## Loading, first-request cost and cache receipts', '', '|Process / arm|Load s|Import + setup s|Warmup request s|Cache hits/misses|Final model device|', '|---|---:|---:|---:|---|---|']
folders=sorted({Path(r['measurement']).parent.parent for r in d['rows']})
for folder in folders:
 load=json.loads((folder/'load.json').read_text());warm=[r for r in d['rows'] if r['first_model_request'] and Path(r['measurement']).parent.parent==folder]
 cache=json.loads((folder/'cache.json').read_text()) if (folder/'cache.json').exists() else {}
 clean=json.loads((folder/'cleanup.json').read_text()) if (folder/'cleanup.json').exists() else {}
 lines.append(f"|{folder.name}|{load['seconds']:.3f}|{load['imports_and_setup_seconds']:.3f}|{warm[0]['request_seconds'] if warm else float('nan'):.3f}|{cache.get('hits','—')}/{cache.get('misses','—')}|{clean.get('model_device','pending')}|")
lines+=['', 'Cache counts refer to CCD/full-feature hooks; parsed artifact caches have their own saved directories. Model cleanup receipts confirm the model returned to CPU after the resident session. This is not a long-duration leak test.', '',
 '## Scope and reproduction', '',
 'Experimental hooks only: no app defaults or installed runtime packages were changed. These results support production candidates, not automatic promotion. Untested: other proteins/lengths, complexes, templates, ligands, varying MSA caps, variable-length design campaigns, cancellation/restart with these hooks, long memory soak, other Macs. Feature/artifact caches are deliberately narrow and require bounded storage and complete scientific keys before product integration.', '',
 'Repository base commit: 00d299abf6f0b93cf1e4f0fff365e196edefb8ca, with pre-existing dirty work preserved. Frozen source hashes identify the actual experimental code. Boltz/IntelliFold use the pinned Torch 2.14 runtimes; OpenFold uses its pinned Torch 2.6 / MLX runtime. Recycles: Boltz 3, OpenFold 3, IntelliFold Flash/Full 10. See frozen manifests for full engine fingerprints.', '',
 'Fresh controls and all experimental arms were serialized through Studio immutable broker plans and the shared GPU lock. Frozen configs retain runtime/interpreter versions, MSA hashes, source provenance and hardware. The original harness-path failure and one teardown-closure failure are preserved; corrected follow-ups completed independently. The biotin job remained paused. Temporary caffeinate assertions prevented idle sleep during testing; system power settings were not changed.', '',
 'Run analyse.py, audit_batch.py, then write_report.py from Validation/experiments/sumo_request_overhead_v1 with the recorded analysis environment. Raw outputs remain under the corresponding sumo_request_overhead_v1* directories. See project Lab Book 0229 and Validation Lab Book 0061.', '',
 '[Overview](OVERVIEW.svg) · [Batch throughput](BATCH_THROUGHPUT.svg) · [Numerical audit](analysis/results.json) · [Batch audit](analysis/batch_results.json)', '']
(OUT/'REPORT.md').write_text('\n'.join(lines))
print(OUT/'REPORT.md')
