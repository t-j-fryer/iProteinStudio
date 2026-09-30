"""Read-only paired workstation/Mac filtering comparison; no inference."""
import os
os.environ.setdefault('MPLCONFIGDIR', '/tmp/iprotein-filtering-mpl')
import argparse, hashlib, json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr
from sklearn.metrics import average_precision_score, roc_auc_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = ROOT / 'Validation/output/paper_binder_matrix_v1/campaign'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def boolean(s): return s.astype(str).str.lower().isin(['true','1'])
def recovery(y,s):
    order=np.argsort(-s,kind='stable');s=s[order];y=np.asarray(y,float)[order]
    starts=np.r_[0,np.flatnonzero(np.diff(s)!=0)+1];ends=np.r_[starts[1:],len(y)]
    return np.repeat(np.add.reduceat(y,starts)/(ends-starts),ends-starts).cumsum()
def membership(s,k):
    cutoff=np.sort(s)[-k];hi=s>cutoff;eq=s==cutoff
    return hi.astype(float)+eq*(k-hi.sum())/eq.sum()
def stats(y,s):
    r=recovery(y,s);p=int(y.sum());n=len(y)
    result=dict(n=n,hits=p,prevalence=p/n,ap=average_precision_score(y,s) if 0<p<n else np.nan,
                auc=roc_auc_score(y,s) if 0<p<n else np.nan)
    for k in [10,20,50,100]:
        if n>=k:
            result.update({f'hits{k}':r[k-1],f'precision{k}':r[k-1]/k,f'recall{k}':r[k-1]/p if p else np.nan})
    return result
def bootstrap(df,w,m,label,n=2000):
    rng=np.random.default_rng(20260930)
    groups=[np.asarray(v) for v in df.groupby('target').indices.values()]
    y=df[label].to_numpy(int);a=df[w].to_numpy(float);b=df[m].to_numpy(float);ds=[];hs=[]
    for _ in range(n):
        idx=np.concatenate([rng.choice(g,len(g),replace=True) for g in groups]);yy=y[idx]
        if 0<yy.sum()<len(yy):
            ds.append(average_precision_score(yy,b[idx])-average_precision_score(yy,a[idx]))
            if len(yy)>=50:hs.append(recovery(yy,b[idx])[49]-recovery(yy,a[idx])[49])
    return dict(ap_delta_ci_low=float(np.quantile(ds,.025)),ap_delta_ci_high=float(np.quantile(ds,.975)),
                hits50_delta_ci_low=float(np.quantile(hs,.025)),hits50_delta_ci_high=float(np.quantile(hs,.975)),bootstrap_replicates=len(ds))

def eta(out):
    cfg=json.loads((CAMPAIGN/'frozen/config.json').read_text());now=datetime.now(timezone.utc);rows=[]; remaining_total=0
    history={'protenix_constraint':('compute_cache','diffcache'),'protenix_v2':('compute_cache','baseline'),
             'esmfold2_fast':('esm_memory','cache4g'),'esmfold2_full':('esm_memory','cache4g')}
    for eng,var in cfg['arms']:
        units=[]
        for p in (CAMPAIGN/f'{eng}__{var}').glob('*/complete.json'):
            f=p.with_name('measurement.json');x=json.loads(f.read_text())
            if not x['warmup'] and not x['diagnostic']:
                assert json.loads(p.read_text())['files'][str(f.resolve())]==sha(f)
                units.append(x)
        n=len(units);left=674-n
        source='current campaign mean'; seconds=np.mean([x['request_seconds'] for x in units]) if units else None
        if not units and eng in history:
            phase,v=history[eng];j=json.loads((CAMPAIGN.parent/phase/'analysis/results.json').read_text())
            us=[x for x in j['rows'] if x['engine']==eng and x['variant']==v and not x['warmup'] and not x['diagnostic']]
            seconds=np.mean([x['request_seconds'] for x in us]);source=f'five SUMO-complex qualification means: {phase}/{v}'
        rem=float(seconds*left) if seconds is not None else None
        if rem:remaining_total+=rem
        rows.append(dict(engine=eng,completed=n,total=674,remaining=left,mean_seconds=float(seconds) if seconds is not None else None,
                         median_seconds=float(np.median([x['request_seconds'] for x in units])) if units else None,forecast_seconds=rem,forecast_basis=source))
    # Planning envelope only; not a statistical prediction interval.
    obj=dict(timestamp_utc=now.isoformat(),engines=rows,total_completed=sum(x['completed'] for x in rows),total_planned=5392,
             central_remaining_hours=remaining_total/3600*1.1,planning_range_hours=[remaining_total/3600*.7,remaining_total/3600*1.6],
             central_finish_utc=(now+timedelta(seconds=remaining_total*1.1)).isoformat(),
             assumption='Queued engines use five SUMO-complex qualification means; add10% central orchestration allowance. Range0.7–1.6x is judgement, not CI; new target lengths, system drift, retries and audit may change finish.')
    (out/'progress_eta.json').write_text(json.dumps(obj,indent=2)+'\n');return obj

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workstation',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True);snap=out/'inputs';snap.mkdir(exist_ok=True)
    sources={'mac.csv':CAMPAIGN/'analysis/predictions.csv','master.csv':args.workstation/'data/paper_design_master_table.csv',
             'headlines.csv':args.workstation/'data/F2_overall_plus_breakdown_summary.csv',
             'operating_points.csv':args.workstation/'data/F2_model_threshold_exploratory_operating_points.csv',
             'workstation_raw.csv':args.workstation/'inputs/boltz_intelli/boltz_intelli_per_design_metrics.csv'}
    hashes={}
    for name,p in sources.items():
        data=p.read_bytes();(snap/name).write_bytes(data);hashes[name]=dict(source=str(p),sha256=hashlib.sha256(data).hexdigest())
    master=pd.read_csv(snap/'master.csv');mac=pd.read_csv(snap/'mac.csv');assert not master.design_name.duplicated().any();assert not mac.duplicated(['prediction_engine','design_name']).any()
    for k in ['included_clean_monoclonal_primary_screen','affinity_validated_hit','clean_monoclonal_primary_screen_hit']:
        master[k]=boolean(master[k])
    cohort=master[master.included_clean_monoclonal_primary_screen];assert len(cohort)==563 and cohort.affinity_validated_hit.sum()==85
    raw=pd.read_csv(snap/'workstation_raw.csv');assert not raw.duplicated(['engine','source_name']).any()
    sys.path.insert(0,str(ROOT/'Validation/experiments/paper_binder_matrix_v1'))
    from analyse import confidence
    paired=[];join_audit=[]
    for engine,prefix,display,headline in [('boltz','boltz2_potentials','Boltz2','p90'),('intellifold_flash','intellifold_flash','IntelliFold Flash','min')]:
        part=mac[mac.prediction_engine.eq(engine)].copy();assert len(part)==674
        # Independent master rejoin, never use copied label fields without checking.
        joined=master.merge(part[['design_name']+[c for c in part if c.startswith('prediction_')]],on='design_name',validate='one_to_one').copy()
        wr=raw[raw.engine.eq(prefix)].set_index('source_name').loc[joined.design_name]
        expected=joined.target_amino_acid_sequence.where(~joined.target.eq('SUMO'),json.loads((CAMPAIGN/'frozen/config.json').read_text())['sequence'])
        assert (expected.str.len().to_numpy()==wr.target_length.to_numpy()).all()
        assert (joined.designed_binder_amino_acid_sequence.str.len().to_numpy()==wr.binder_length.to_numpy()).all()
        assert (expected.map(lambda s:hashlib.sha1(s.encode()).hexdigest()[:10]).to_numpy()==wr.target_id.str.rsplit('__',n=1).str[-1].to_numpy()).all()
        joined['engine']=engine;joined['display']=display
        for metric in ['iptm','ipsae_min']:
            for agg in ['median',headline]:
                joined[f'work_{metric}_{agg}']=wr[f'complex_{metric}_{agg}'].to_numpy() if f'complex_{metric}_{agg}' in wr else np.nan
        joined['work_ipae']=wr.complex_ipae_mean_angstrom_median.to_numpy()
        joined['work_binder_plddt']=wr.complex_binder_plddt_mean_median.to_numpy()
        joined['mac_ipae']=np.nan;joined['mac_binder_plddt']=np.nan
        for idx,row in joined.iterrows():
            f=Path(row.prediction_measurement);assert sha(f)==row.prediction_measurement_sha256
            values=confidence(Path(row.prediction_structure));n=int(row.prediction_binder_length);total=n+int(row.prediction_target_length)
            pae=next(v for k,v in values.items() if 'pae' in k).squeeze();assert pae.shape==(total,total)
            joined.loc[idx,'mac_ipae']=(pae[:n,n:].mean()+pae[n:,:n].mean())/2
            pl=next((v.squeeze() for k,v in values.items() if 'plddt' in k and v.size==total),None)
            if pl is not None:joined.loc[idx,'mac_binder_plddt']=pl[:n].mean()
        joined['work_headline']=joined[f'work_ipsae_min_{headline}'];joined['mac_headline']=joined.prediction_ipsae_min
        joined['assayed_sequence_differs']=joined.assayed_binder_amino_acid_sequence.notna() & joined.assayed_binder_amino_acid_sequence.ne(joined.designed_binder_amino_acid_sequence)
        paired.append(joined);join_audit.append(dict(engine=engine,n=len(joined),unique_names=True,target_hashes=True,binder_lengths=True,binder_sequence_verified_in_workstation_export=False))
    allpairs=pd.concat(paired,ignore_index=True)
    keep=['engine','display','design_name','target','campaign','included_clean_monoclonal_primary_screen','affinity_validated_hit','clean_monoclonal_primary_screen_hit','assayed_sequence_differs','work_headline','mac_headline','work_iptm_median','prediction_iptm','work_ipsae_min_median','prediction_ipsae_min','work_ipae','mac_ipae','work_binder_plddt','mac_binder_plddt']
    allpairs[keep].to_csv(out/'paired_design_scores.csv',index=False)
    correlations=[];summary=[];thresholds=[];curves=[];overlap=[];boots=[]
    mappings=[('ipTM','work_iptm_median','prediction_iptm',1),('ipSAE median','work_ipsae_min_median','prediction_ipsae_min',1),('mean interface PAE','work_ipae','mac_ipae',-1),('binder pLDDT','work_binder_plddt','mac_binder_plddt',1),('F2 fixed score','work_headline','mac_headline',1)]
    for eng,d in allpairs.groupby('engine',sort=False):
        for pop,mask in [('all_predicted',np.ones(len(d),bool)),('clean_primary',d.included_clean_monoclonal_primary_screen)]:
            for target in ['All',*sorted(d.target.unique())]:
                z=d.loc[mask & (True if target=='All' else d.target.eq(target))]
                for metric,w,m,sign in mappings:
                    use=z[[w,m]].dropna();n=len(use)
                    if n>2 and use[w].nunique()>1 and use[m].nunique()>1:
                        correlations.append(dict(engine=eng,population=pop,target=target,metric=metric,n=n,spearman=spearmanr(use[w],use[m]).statistic,pearson=pearsonr(use[w],use[m]).statistic,mean_mac_minus_work=(use[m]-use[w]).mean(),mae=(use[m]-use[w]).abs().mean()))
        masks={'clean_primary':d.included_clean_monoclonal_primary_screen,
               'strict':d.included_clean_monoclonal_primary_screen & (d.affinity_validated_hit | ~d.clean_monoclonal_primary_screen_hit),
               'assayed_sequence_matches':d.included_clean_monoclonal_primary_screen & ~d.assayed_sequence_differs}
        for pop,mask in masks.items():
            for target in ['All',*sorted(d.target.unique())]:
                z=d.loc[mask & (True if target=='All' else d.target.eq(target))].copy()
                if not len(z):continue
                for metric,w,m,sign in mappings:
                    q=z.dropna(subset=[w,m]);y=q.affinity_validated_hit.to_numpy(int)
                    if not len(q):continue
                    for platform,col in [('workstation',w),('mac',m)]:
                        s=q[col].to_numpy(float)*sign
                        summary.append(dict(engine=eng,population=pop,target=target,metric=metric,platform=platform,**stats(y,s)))
                        if metric=='F2 fixed score' and pop=='clean_primary':
                            rec=recovery(y,s)
                            curves.extend(dict(engine=eng,target=target,platform=platform,k=k,hits=h,precision=h/k,recall=h/y.sum() if y.sum() else np.nan) for k,h in enumerate(rec,1))
                    if target=='All' and pop in ['clean_primary','strict'] and metric in ['F2 fixed score','ipSAE median']:
                        boots.append(dict(engine=eng,population=pop,metric=metric,**bootstrap(q.reset_index(drop=True),w,m,'affinity_validated_hit')))
                if target=='All' and pop=='clean_primary':
                    # Reproduce the historical F2 score without reselecting the metric.
                    old=pd.read_csv(snap/'headlines.csv');label='Boltz-2 (potentials)' if eng=='boltz' else 'IntelliFold Flash'
                    old=old[old.model.eq(label)&old.target.eq('All')].iloc[0]
                    assert abs(stats(z.affinity_validated_hit.to_numpy(int),z.work_headline.to_numpy())['ap']-old.average_precision)<1e-12
                    for k in [10,20,50,100]:
                        a=membership(z.work_headline.to_numpy(),k);b=membership(z.mac_headline.to_numpy(),k)
                        overlap.append(dict(engine=eng,k=k,expected_shared_designs=float((a*b).sum()),expected_shared_validated=float((a*b*z.affinity_validated_hit).sum())))
            # Fixed threshold transfer: no Mac threshold optimization.
            z=d.loc[mask];y=z.affinity_validated_hit.to_numpy(int);ops=pd.read_csv(snap/'operating_points.csv');label='Boltz-2 (potentials)' if eng=='boltz' else 'IntelliFold Flash';cut=float(ops[ops.model.eq(label)&ops.target.eq('All')].iloc[0].threshold)
            for t in [.2,.4,.6,.8,cut]:
                for platform,col in [('workstation','work_headline'),('mac','mac_headline')]:
                    selected=z[col].to_numpy()>=t;tp=int(y[selected].sum());n=int(selected.sum())
                    thresholds.append(dict(engine=eng,population=pop,platform=platform,threshold=t,workstation_exploratory_cutoff=t==cut,passing=n,validated=tp,precision=tp/n if n else np.nan,recall=tp/y.sum()))
        # Secondary experimental endpoint: primary-screen positivity.
        z=d[d.included_clean_monoclonal_primary_screen]
        for platform,col in [('workstation','work_headline'),('mac','mac_headline')]:
            summary.append(dict(engine=eng,population='primary_screen_positive_endpoint',target='All',metric='F2 fixed score',platform=platform,**stats(z.clean_monoclonal_primary_screen_hit.to_numpy(int),z[col].to_numpy())))
    frames={k:pd.DataFrame(v) for k,v in [('correlations',correlations),('filtering_metrics',summary),('paired_bootstrap',boots),('threshold_transfer',thresholds),('recovery_curves',curves),('shortlist_overlap',overlap)]}
    for name,df in frames.items():df.to_csv(out/(name+'.csv'),index=False)
    progress=eta(out)
    provenance=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),sources=hashes,join_audit=join_audit,cohort=563,validated=85,engines=['boltz','intellifold_flash'],bootstrap='2000 paired design resamples within target; fixed metric selection; does not account for related design families',new_predictions=0,metric_provenance='Mac ipSAE: Dunbrack v4 d0res directional minimum, PAE<10A; workstation implementation/cutoff incompletely documented. Aggregation across samples distinct from directional min.',confounds=['Boltz potentials workstation on versus Mac off','Mac one seed versus workstation sample aggregates of undocumented count','workstation run settings/commits incompletely recorded','experimental verification/metric-selection biases','workstation binder sequences unavailable; exact names+lengths and target sequence hashes verified'])
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    plot(out,allpairs,frames)
    print(frames['filtering_metrics'].query("population=='clean_primary' and target=='All' and metric=='F2 fixed score'").to_string(index=False))
    print(frames['paired_bootstrap'].to_string(index=False));print(json.dumps(progress,indent=2))

def plot(out,data,f):
    plt.rcParams.update({'font.family':'Arial','font.size':9,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'xtick.direction':'in','ytick.direction':'in'})
    fig,axs=plt.subplots(2,3,figsize=(13,7.5),layout='constrained')
    for axrow,(eng,d) in zip(axs,data.groupby('engine',sort=False)):
        z=d[d.included_clean_monoclonal_primary_screen];a,b,c=axrow;y=z.affinity_validated_hit
        a.scatter(z.work_ipsae_min_median[~y],z.prediction_ipsae_min[~y],s=10,color='#8b8b8b',alpha=.35)
        a.scatter(z.work_ipsae_min_median[y],z.prediction_ipsae_min[y],s=15,color='#bc5a33',alpha=.8,label='Validated hit')
        a.plot([0,1],[0,1],color='black',lw=.6,ls=':');a.set(xlabel='Workstation ipSAE directional min\nmedian across samples',ylabel='Mac ipSAE directional min\none sample',xlim=(0,1),ylim=(0,1))
        r=f['correlations'].query("population=='clean_primary' and target=='All' and metric=='ipSAE median'");r=r[r.engine.eq(eng)].iloc[0]
        a.set_title(f"{d.display.iloc[0]}: score agreement\nSpearman ρ={r.spearman:.3f}; n={len(z)}")
        s=f['filtering_metrics'];s=s[s.engine.eq(eng)&s.population.eq('clean_primary')&s.target.eq('All')&s.metric.eq('F2 fixed score')].set_index('platform')
        for platform,color,label in [('workstation','#536b91','Workstation'),('mac','#bc5a33','Mac')]:
            cr=f['recovery_curves'];cr=cr[cr.engine.eq(eng)&cr.target.eq('All')&cr.platform.eq(platform)]
            b.plot(cr.k,cr.hits,color=color,label=f'{label}: AP {s.loc[platform,"ap"]:.3f}');c.plot(cr.recall,cr.precision,color=color,label=label)
        b.plot([0,563],[0,85],color='black',ls=':',lw=.8);b.set(xlim=(0,150),xlabel='Designs retained',ylabel='Validated hits recovered',title='Historical F2 metric held fixed');b.legend(frameon=False)
        c.axhline(85/563,color='black',ls=':',lw=.8);c.set(xlim=(0,1),ylim=(0,1),xlabel='Recall of validated hits',ylabel='Validated fraction retained',title='Precision–recall by testing budget')
    fig.suptitle('Mac versus workstation: paired retrospective filtering\n563 screened designs / 85 validated hits; Mac ≤128-row target MSA, 25 steps, one sample',fontsize=13)
    fig.supxlabel('Different protocols: workstation Boltz potentials on; Mac off. Workstation summaries pool samples.\nF2 uses Boltz ipSAE p90 and Flash ipSAE sample-min; metric implementation provenance is incomplete.',fontsize=9)
    fig.savefig(out/'OVERVIEW.svg',transparent=True);fig.savefig(out/'OVERVIEW.png',dpi=150);plt.close(fig)

if __name__=='__main__':main()
