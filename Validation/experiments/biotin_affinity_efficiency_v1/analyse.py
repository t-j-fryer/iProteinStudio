"""Report paired score changes separately from seeds, scheduling and history."""
import json
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr, pearsonr
from common import save


def compare(left,right):
    assert set(left)==set(right)
    keys=sorted(left)
    a=np.array([left[k]['pbind'] for k in keys]);b=np.array([right[k]['pbind'] for k in keys])
    delta=b-a
    def correlation(fn):
        if len(set(a))<2 or len(set(b))<2:return None
        return float(fn(a,b).statistic)
    result=dict(n=len(keys),mean_signed_pbind_change=float(delta.mean()),
                mean_absolute_pbind_change=float(np.abs(delta).mean()),
                max_absolute_pbind_change=float(np.abs(delta).max()),
                pearson=correlation(pearsonr),spearman=correlation(spearmanr),
                pbind_shift_gt_005=int((np.abs(delta)>0.05).sum()),
                pbind_threshold_crossings={str(t):int(((a>=t)!=(b>=t)).sum()) for t in (0.2,0.5,0.8)},
                identical_feature_hashes=all(left[k]['feature_sha256']==right[k]['feature_sha256'] for k in keys))
    for metric in ('pbind','score'):
        top=lambda rows:set(sorted(keys,key=lambda k:(-rows[k][metric],k))[:min(10,len(keys))])
        result[metric+'_top10_overlap']=len(top(left)&top(right))
    return result


def analyse(cfg):
    out=Path(cfg['output']);batches=json.loads((out/'affinity_results.json').read_text())['batches']
    index={}
    for batch in batches:
        for row in batch['rows']:
            key=(batch['repeat'],batch['arm']['name'],row['generator'])
            index.setdefault(key,{})[row['key']]=row
    paired=[]
    for repeat in range(2):
        for generator in ('boltz','rfd3'):
            left=index[(repeat,'reference',generator)];right=index[(repeat,'light',generator)]
            assert len(left)==len(right)==24
            row=dict(repeat=repeat,generator=generator,**compare(left,right))
            assert row['identical_feature_hashes'], 'Feature inputs differ between paired settings'
            paired.append(row)
    seed_variation=[]
    for arm in ('reference','light'):
        for generator in ('boltz','rfd3'):
            seed_variation.append(dict(arm=arm,generator=generator,
                                       **compare(index[(0,arm,generator)],index[(1,arm,generator)])))
    same=[]
    for batch in json.loads((out/'same_seed_results.json').read_text())['batches']:
        rows={r['key']:r for r in batch['rows']};generator=batch['rows'][0]['generator'];arm=batch['arm']['name']
        left={k:index[(0,arm,generator)][k] for k in rows}
        same.append(dict(arm=arm,generator=generator,**compare(left,rows)))
    times=[]
    for repeat in range(2):
        vals={arm:sum(b['elapsed_seconds'] for b in batches if b['repeat']==repeat and b['arm']['name']==arm)
              for arm in ('reference','light')}
        times.append(dict(repeat=repeat,seconds_per_design={k:v/48 for k,v in vals.items()},
                          reference_over_light=vals['reference']/vals['light']))
    overlaps=json.loads((out/'overlap_results.json').read_text())['arms'];overlap_audit=[]
    for repeat in range(2):
        serial=next(r for r in overlaps if r['repeat']==repeat and r['mode']=='serial')
        parallel=next(r for r in overlaps if r['repeat']==repeat and r['mode']=='overlap')
        l=lambda a:{r['key']:r['sha256'] for r in a['laser']['rows']}
        g=lambda a:{r['key']:r['result'] for r in a['geometry']['rows']}
        gpu=lambda a:{r['key']:r for r in a['gpu']['rows']}
        row=dict(repeat=repeat,serial_seconds=serial['elapsed_seconds'],overlap_seconds=parallel['elapsed_seconds'],
                 speed_ratio=serial['elapsed_seconds']/parallel['elapsed_seconds'],
                 exact_laser_fasta_scores=l(serial)==l(parallel),exact_geometry=g(serial)==g(parallel),
                 affinity=compare(gpu(serial),gpu(parallel)))
        overlap_audit.append(row)
    result=dict(paired_settings=paired,different_seed_variation=seed_variation,
                same_seed_reproducibility=same,timing=times,overlap=overlap_audit,
                production_default_changed=False)
    save(out/'analysis/summary.json',result)
    lines=['# Saved-biotin affinity and CPU efficiency qualification','',
           '48 designs: 24 per generator, balanced between Phase 0/optimization and historical P(bind) tertiles.',
           'Two distinct seeded repeats; each seed matched across reference200/5 and light50/1. Eight designs also repeated with identical seeds under both settings.',
           'Unchanged saved full-precision geometry, five affinity recycles, ensemble, empty MSA and resident weights. Outer structure prediction is forbidden.',
           '', '| Seed repeat | Generator | n | Mean absolute P(bind) change | Spearman | Top10 P(bind) retained |',
           '|---|---|---:|---:|---:|---:|']
    for r in paired:
        lines.append(f"| {r['repeat']} | {r['generator']} | {r['n']} | {r['mean_absolute_pbind_change']:.4f} | {r['spearman']} | {r['pbind_top10_overlap']} |")
    lines+=['','## Resident request timing','',json.dumps(times,indent=2),
            '', 'Includes features, affinity inference, writer and native audit; excludes initial load, warmup and input staging. Not GPU-kernel-only time.',
            '', '## Reproducibility and CPU overlap','',json.dumps(dict(same_seed=same,overlap=overlap_audit),indent=2),
            '', '## Limits','', 'Score stability is not experimental binding validation. The cohort is stratified, not a population prevalence estimate. CPU overlap uses independent prepared-input replay, not a complete live design cycle. Prepared LASErMPNN inputs exclude protonation. Pool startup and orchestration are included in CPU/overlap wall time. No production settings promoted. See summary.json for thresholds and seed effects.']
    (out/'analysis/REPORT.md').write_text('\n'.join(lines)+'\n')
    if not all(r['exact_laser_fasta_scores'] and r['exact_geometry'] and r['affinity']['identical_feature_hashes'] for r in overlap_audit):
        raise RuntimeError('CPU/GPU overlap equivalence failed; inspect analysis')
    save(out/'completed.json',dict(passed=True,analysis='analysis/summary.json'))


if __name__=='__main__':
    import sys
    analyse(json.loads(Path(sys.argv[1]).read_text()))
