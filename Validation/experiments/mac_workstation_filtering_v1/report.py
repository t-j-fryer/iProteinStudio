"""Render the saved numerical comparison; does not refresh or alter predictions."""
from pathlib import Path
import json,sys
import pandas as pd
from zoneinfo import ZoneInfo
from datetime import datetime

def main():
    out=Path(sys.argv[1]);s=pd.read_csv(out/'filtering_metrics.csv');c=pd.read_csv(out/'correlations.csv');b=pd.read_csv(out/'paired_bootstrap.csv');t=pd.read_csv(out/'threshold_transfer.csv');p=json.loads((out/'progress_eta.json').read_text())
    lines=['# Interim Mac versus workstation filtering comparison','',
    'Snapshot: '+p['timestamp_utc']+'. The Mac job continues; only completed Boltz2 and IntelliFold Flash have paired workstation counterparts available now. No new predictions were launched for this analysis.','',
    '## Main result','',
    'On the existing563-design/85-affinity-validated-hit cohort, the reduced Mac protocol preserves similar pooled average precision and top50/top100 filtering yield for the two completed paired engines. This is encouraging retrospective evidence, not proof of equivalence or an isolated MSA/diffusion experiment. Confidence intervals still allow several AP percentage points of loss. Scores and individual shortlists are not identical; fixed numerical thresholds are less transferable.','',
    '| Engine | AP workstation → Mac | ROC AUC workstation → Mac | Hits/top50 workstation → Mac | Hits/top100 workstation → Mac |','|---|---:|---:|---:|---:|']
    main=s.query("population=='clean_primary' and target=='All' and metric=='F2 fixed score'")
    for e,d in main.groupby('engine',sort=False):
        q=d.set_index('platform');w=q.loc['workstation'];m=q.loc['mac'];lines.append(f'| {e} | {w.ap:.3f} → {m.ap:.3f} | {w.auc:.3f} → {m.auc:.3f} | {w.hits50:.0f} → {m.hits50:.0f} | {w.hits100:.0f} → {m.hits100:.0f} |')
    lines+=['','Mac one-sample ipSAE(min) is compared to the previously selected F2 rules: workstation Boltz sample-p90 of directional-min ipSAE; Flash sample-min of directional-min ipSAE. No score family or direction was selected using the new Mac outcomes. Random ranking prevalence is85/563=15.1%. Top50 precision is36%→48% Boltz and40%→42% Flash; top50 recall is21.2%→28.2% and23.5%→24.7%.','',
    '## Score agreement and matched metric sensitivity','',
    '| Engine | Metric | Spearman rho | Pearson r |','|---|---|---:|---:|']
    for _,r in c.query("population=='clean_primary' and target=='All' and metric!='F2 fixed score'").iterrows():lines.append(f'| {r.engine} | {r.metric} | {r.spearman:.3f} | {r.pearson:.3f} |')
    lines+=['','Correlations use workstation sample medians versus the Mac single prediction; population size563 for each reported row. The separate all674-design and per-target correlations are in correlations.csv. Flash token-level binder pLDDT could not be matched to a residue-length vector by the shared reader, so that correlation is omitted rather than substituting whole-complex confidence.','',
    'Using workstation median ipSAE for BOTH engines gives AP0.359→0.375 for Boltz and0.376→0.384 for Flash. Thus the headline conclusion is not dependent on comparing against the historically chosen p90/min aggregation. The aggregation/sampling budgets remain unequal; there is no raw workstation single-seed control in this export.','',
    '## Paired uncertainty','',
    '2,000 paired design-level bootstrap replicates within target, keeping both platforms on the same resampled designs. Intervals are descriptive95% percentile intervals; they do not account for related design families, historical metric selection or verification bias.','',
    '| Engine | Cohort | Mac − workstation AP,95% interval |','|---|---|---:|']
    for _,r in b[b.metric.eq('F2 fixed score')].iterrows():lines.append(f'| {r.engine} | {r.population} | [{r.ap_delta_ci_low:.3f}, {r.ap_delta_ci_high:.3f}] |')
    lines+=['','Pooled AP differences are+0.0083 Boltz and−0.0098 Flash. Both intervals include zero; this is not a formal noninferiority result and no materiality margin was prespecified. A5-percentage-point AP degradation is still compatible with the Flash interval.','',
    '## Target-specific changes','',
    '| Target | Designs / hits | Boltz AP workstation → Mac | Flash AP workstation → Mac |','|---|---:|---:|---:|']
    sub=s.query("population=='clean_primary' and target!='All' and metric=='F2 fixed score'")
    for target,d in sub.groupby('target',sort=False):
        vals=[]
        for e in ['boltz','intellifold_flash']:
            q=d[d.engine.eq(e)].set_index('platform');w=q.loc['workstation'];m=q.loc['mac'];vals.append('undefined: no hits' if pd.isna(w.ap) else f'{w.ap:.3f} → {m.ap:.3f}')
        r=d.iloc[0];lines.append(f'| {target} | {r.n}/{r.hits} | {vals[0]} | {vals[1]} |')
    lines+=['','SUMO dominates the cohort and shows some loss: Boltz AP0.463→0.437 and Flash0.413→0.371, despite SUMO top50 recovery24→24 and21→22. Improvements on smaller ProteinA/TrxA groups offset this in pooled AP. ProteinA/ALFA have only four validated hits each, so changes are particularly unstable. Myc has no validated positives and undefined AP/recall.','',
    '## Threshold transfer and shortlist identity','',
    '| Engine | Historical workstation cutoff | Platform | Passing / validated | Precision | Recall |','|---|---:|---|---:|---:|---:|']
    for _,r in t.query("population=='clean_primary' and workstation_exploratory_cutoff").iterrows():lines.append(f'| {r.engine} | {r.threshold:.6f} | {r.platform} | {r.passing}/{r.validated} | {r.precision:.1%} | {r.recall:.1%} |')
    lines+=['','These cutoffs were selected retrospectively by the workstation analysis and were transferred unchanged; they are not newly recommended cutoffs. The Boltz threshold comparison also changes sample aggregation (p90→single), explaining why threshold transfer is a different question from ranking quality.','',
    'Top50 design overlap is34/50 for Boltz and38/50 for Flash. Shared validated hits are16 and15 respectively. Consequently similar total hit yield does not imply recovery of the same binders. Exact score ties receive expected random tie-breaking, matching the workstation method.','',
    '## Cohort and experimental-label sensitivity','',
    'The independent reanalysis assay inputs reproduce all three master-table label sets exactly. The strict550-design cohort removes primary-screen positives without affinity validation and retains85 validated hits: AP0.384→0.386 Boltz;0.414→0.396 Flash. The primary-screen-positive endpoint (87/563), rather than affinity validation, gives AP0.391→0.377 and0.414→0.391.','',
    'There are32 screened designs whose reported assayed sequence differs from the designed sequence; all32 are validated hits. Both computational workflows score the design identifiers, and the Mac explicitly predicts the designed sequence. Excluding those32 gives531 designs/53 hits: AP0.319→0.369 Boltz and0.372→0.366 Flash. This exclusion is strongly outcome-associated and is only a sensitivity analysis, not a replacement primary cohort. Missing assayed sequence metadata are not proof of exact sequence identity.','',
    '## What this can establish','',
    '- Both completed engines have674 uniquely matched design names. Target sequence hash/length and binder length match the workstation exports; the Mac structure/measurement export has independent integrity audits. Workstation exports lack binder sequences, so binder identity cannot be independently reverified beyond identifier/length.','- Mac uses at most128 target alignment records,25 diffusion steps,one seed/sample, query-only binder and exact token sizing. Small peptide-tag alignments contain query duplicates, not homolog support.','- Workstation Boltz explicitly uses potentials; Mac has potentials off. Workstation sample counts, complete run settings, source commits and ipSAE implementation/cutoff are not fully recorded in these exports. Therefore do not attribute observed differences specifically to MSA depth, step count, hardware or our patches.','- Mac ipSAE uses Dunbrack v4 d0res, PAE<10Å and the conservative directional minimum. Workstation fields have analogous names but incomplete implementation provenance. ipTM agreement provides an additional native-metric comparison.','- The SUMO workstation target was independently audited as96aa in the prior source report; current Boltz/Flash target hashes also match the Mac target. A69aa design-structure construct is not being confused with these prediction inputs.','- All metrics are retrospective on a previously selected campaign. Unvalidated designs are benchmark non-hits, not necessarily true biological nonbinders. No newly generated population or independent experimental validation is established.','- OpenFold is complete but openDDE is a different model, not a valid paired engine. Mac Protenixv2 and ESMFull/Fast remain pending; Mini/Constraint lack counterparts in this supplied table. IntelliFold Full is not part of the ongoing Mac campaign.','',
    '## Campaign progress and finish estimate','',f"At {p['timestamp_utc']}: {p['total_completed']}/{p['total_planned']} saved normal outputs. Counts verify checkpoint/measurement hashes; the earlier fully exported2022 predictions have zero independent output-audit errors. This update does not claim the pending Mini outputs have undergone the same full report audit yet.",'',
    '| Engine | Completed | Estimated remaining compute, hours | Basis |','|---|---:|---:|---|']
    for r in p['engines']:lines.append(f"| {r['engine']} | {r['completed']}/674 | {(r['forecast_seconds'] or 0)/3600:.2f} | {r['forecast_basis']} |")
    end=datetime.fromisoformat(p['central_finish_utc']).astimezone(ZoneInfo('America/New_York'))
    lines+=['',f"Central planning estimate: about{p['central_remaining_hours']:.0f}h remaining, approximately {end.strftime('%A %B %d, %I:%M %p %Z')}. Practical range about{p['planning_range_hours'][0]:.0f}–{p['planning_range_hours'][1]:.0f}h. This range is judgement, not a statistical interval.",'',
    'Means rather than medians estimate total work. Pending-engine means come from five actual qualification complexes and may be poor predictors of other targets/lengths. Central estimate adds10% for orchestration; future system drift, complex size, retries and final analysis can move the finish substantially. OpenFold already recovered from one−9 worker exit and completed on its automatic retry; this analysis does not diagnose the cause or change any jobs.','',
    '## Files and reproduction','',
    'OVERVIEW.svg/png; paired_design_scores.csv; correlations.csv; filtering_metrics.csv; paired_bootstrap.csv; threshold_transfer.csv; recovery_curves.csv; shortlist_overlap.csv; progress_eta.json; provenance.json; validation.json. Source CSV snapshots and checksums preserve this interim result. No source workstation files or prediction outputs were modified.','',
    'Run analyse.py with explicit --workstation and a NEW --output snapshot directory, then report.py OUTPUT. Use the qualified CPU analysis environment; no engine/model import or new GPU inference is required. For engines completing later, add their appropriate metric/protocol mappings before comparing them.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
