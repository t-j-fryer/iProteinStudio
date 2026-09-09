#!/usr/bin/env python3
"""Paired full-cohort seed interventions against the fixed audited mixed control.

The four factorial cells share trajectory seeds, prediction/design parameters,
seed grammar/mask RNG, and scientific code hashes. No best-cycle selection.
"""
import argparse
import csv
import importlib.util
import json
import statistics
from pathlib import Path
import numpy as np
from biotite.structure.io.pdbx import CIFFile, get_structure
from diagnose import summarize_structure, sha256, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('prior_seed_summary', HERE.parent/'secondary_structure_seed_mask_v1/summary.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
REFERENCE = 'mixed_seed_only'
ARMS = ('mixed_low_turn', 'mixed_mild_anti', 'mixed_low_turn_mild_anti')
EXPECTED = {REFERENCE:(.5,.5), ARMS[0]:(.5,.1), ARMS[1]:(.25,.5), ARMS[2]:(.25,.1)}
EXTRA_METRICS = ('coil_confidence_below50_fraction','coil_confidence_50to70_fraction','coil_confidence_70plus_fraction','coil_length_16+_fraction','long_coil_mean_below60_fraction','coil_internal_fraction')
METRICS = prior.METRICS + EXTRA_METRICS


def read_source(root, wanted_arms):
    analysis=root/'analysis/full'
    paths={'audit':analysis/'audit.json','manifest':root/'manifest_full.json','structures':analysis/'audited_per_structure.csv','trajectories':analysis/'audited_per_trajectory.csv'}
    report=json.loads(paths['audit'].read_text());manifest=json.loads(paths['manifest'].read_text())
    require(report.get('passed') is True and report.get('all_complete') is True,'source operational audit incomplete')
    config=manifest['config']; campaign=config['campaign']
    require(manifest['phase']=='full' and campaign['full_trajectories']==10 and campaign['design_cycles']==5 and campaign['binder_length']==90,'requires full ten-by-five 90-residue campaign')
    require(set(wanted_arms)<=set(config['arms']),'requested arms absent')
    require(report['audited_structures']==report['expected_structures']==60*len(config['arms']),'incorrect full audit cardinality')
    # Recheck every immutable input/output covered by the completed audit before
    # trusting derived CSVs. This includes coordinates, manifests, seed plans,
    # confidence files, copied scientific code, and execution receipts.
    for label,digest in report['raw_sha256'].items():
        path = Path(manifest['runtime']['root'])/'agent/jobs'/Path(label).stem/'state.json' if label.startswith('job_state/') else root/label
        require(sha256(path)==digest,f'audited source changed: {path}')
    rows=list(csv.DictReader(paths['structures'].open()))
    require(len(rows)==report['audited_structures'],'structure CSV cardinality mismatch')
    selected=[]
    for arm in wanted_arms:
        group=[r for r in rows if r['arm']==arm]
        wanted={(f'run_{i:03d}',c) for i in range(1,11) for c in range(6)}
        require(len(group)==60 and {(r['run'],int(r['cycle'])) for r in group}==wanted,'missing/duplicate trajectory cycles')
        require(report['arm_audits'][arm]['audit_status']=='audited_complete','arm audit is not complete')
        for row in group:
            numeric=dict(arm=arm,run=row['run'],cycle=int(row['cycle']),**{k:float(row[k]) for k in prior.METRICS})
            require(all(np.isfinite(numeric[k]) for k in prior.METRICS),'nonfinite summary input')
            # Recheck saved sequence/P-SEA fractions, confidence and diagnostics
            # against coordinate data whose immutable hash was just verified.
            require(row['structure']==f"campaigns/full__{arm}/{row['run']}/cycle_{numeric['cycle']:02d}/pred_min/model_0.cif",'coordinate path does not match declared trajectory/cycle')
            require(row['confidence']==str(Path(row['structure']).with_name('confidence.json')),'confidence path does not match coordinates')
            path=root/row['structure'];atoms=get_structure(CIFFile.read(path),model=1,extra_fields=['b_factor'])
            chain=atoms[atoms.chain_id=='A'];ca=chain[chain.atom_name=='CA']
            from biotite.structure import annotate_sse
            from biotite.sequence import ProteinSequence
            sequence=''.join('X' if name=='UNK' else ProteinSequence.convert_letter_3to1(name) for name in ca.res_name)
            require(sequence==row['sequence'],'CSV/coordinate sequence mismatch')
            codes=''.join(annotate_sse(chain));require(codes==row['psea'],'CSV/coordinate P-SEA mismatch')
            plan=report['arm_audits'][arm]['seed_plans'][row['run']]
            _,_,diagnostics=summarize_structure(codes,np.asarray(ca.b_factor,dtype=float),plan)
            for k in ('helix_fraction','sheet_fraction','coil_fraction'):
                require(abs(numeric[k]-diagnostics[k])<1e-10,'structure CSV fraction mismatch')
            require(abs(numeric['binder_plddt']-diagnostics['binder_plddt']/100)<1e-9,'structure CSV confidence mismatch')
            confidence=json.loads((root/row['confidence']).read_text())
            for key in ('iptm','ipsae_min','complex_plddt'):
                require(abs(numeric[key]-float(confidence[key]))<1e-9,f'CSV/per-structure confidence differs: {key}')
            from audit_seed import audit as seed_audit
            composition=seed_audit.composition(sequence)
            for key in ('sequence_entropy_bits','max_residue_fraction','max_identical_residue_run'):
                require(abs(numeric[key]-composition[key])<1e-9,f'CSV/sequence composition differs: {key}')
            numeric.update({k:diagnostics[k] for k in EXTRA_METRICS})
            selected.append(numeric)
        for metric in prior.METRICS:
            for endpoint,predicate in [('optimized_cycle_mean',lambda c:c>0),('final_cycle',lambda c:c==5)]:
                actual=statistics.mean(float(r[metric]) for r in group if predicate(int(r['cycle'])))
                expected=report['arms'][arm]['endpoints'][endpoint][metric]
                require(abs(actual-expected)<1e-9,f'CSV differs from audited endpoint: {arm}/{metric}')
    return dict(root=str(root),report=report,manifest=manifest,rows=selected,input_sha256={name:sha256(path) for name,path in paths.items()})


def comparable_arguments(arguments):
    """Remove only declared strength contrasts and campaign-specific paths."""
    ignored={'--anti-helix-strength','--turn-strength','--template-yaml','--run-name','--out-root'}
    result=[];index=0
    while index<len(arguments):
        if arguments[index] in ignored:
            require(index+1<len(arguments),'missing ignored argument value')
            index+=2
        else:
            result.append(arguments[index]);index+=1
    return result


def validate_pairing(reference, intervention):
    first,second=reference['manifest'],intervention['manifest']
    declared=second['config'].get('reference_control',{})
    require(declared.get('arm')==REFERENCE,'unexpected declared reference arm')
    require(declared.get('manifest_sha256')==reference['input_sha256']['manifest'],'declared reference manifest changed')
    require(declared.get('audit_sha256')==reference['input_sha256']['audit'],'declared reference audit changed')
    for key in ('runner_sha256','secondary_helper_sha256','target_msa_sha256','template_sha256'):
        require(first['runtime'][key]==second['runtime'][key],f'paired scientific runtime differs: {key}')
    require(first['engine_fingerprints']==second['engine_fingerprints'],'model/engine fingerprints differ')
    for key in ('binder_length','binder_seed','mpnn_seed','predictor_seed','predictor_samples','design_cycles','full_trajectories'):
        require(first['config']['campaign'][key]==second['config']['campaign'][key],f'paired campaign differs: {key}')
    require(first['config']['target']==second['config']['target'],'target differs')
    require(first['config']['initialization']==second['config']['initialization'],'initialization differs')
    for source,arms in ((reference,(REFERENCE,)),(intervention,ARMS)):
        for arm in arms:
            settings=source['manifest']['config']['arms'][arm]
            anti,turn=EXPECTED[arm]
            require(settings['mode']=='mixed' and settings['scope']=='seed-only','unexpected intervention scope')
            require(settings['anti_helix_strength']==anti and settings['turn_strength']==turn,'unexpected factorial setting')
            require(settings['beta_strength']==settings['beta_pattern_strength']==1,'beta settings differ')
            request=json.loads((Path(source['root'])/'plans/full'/f'{arm}.json').read_text())['normalized_request']['arguments']
            baseline_request=json.loads((Path(reference['root'])/'plans/full'/f'{REFERENCE}.json').read_text())['normalized_request']['arguments']
            require(comparable_arguments(request)==comparable_arguments(baseline_request),'nonintervention prediction/design arguments differ')
            plans=source['report']['arm_audits'][arm]['seed_plans']
            for run,plan in plans.items():
                baseline=reference['report']['arm_audits'][REFERENCE]['seed_plans'][run]
                require(plan['seed']==baseline['seed'] and plan['positions']==baseline['positions'] and plan['blocks']==baseline['blocks'] and plan['x_positions']==baseline['x_positions'],'paired seed/grammar/mask differs')


def contrast(values):
    return {metric:prior.paired_bootstrap([row[metric] for row in values]) for metric in METRICS}


def build_summary(rows):
    output={}
    for endpoint,cycles in [('optimized_cycles01_05',range(1,6)),('cycle05',[5]),('cycle00',[0])]:
        by_arm={arm:{} for arm in EXPECTED}
        for arm in EXPECTED:
            for run in [f'run_{i:03d}' for i in range(1,11)]:
                group=[r for r in rows if r['arm']==arm and r['run']==run and r['cycle'] in cycles]
                require(len(group)==len(cycles),'endpoint missing required cycles')
                by_arm[arm][run]={k:statistics.mean(r[k] for r in group) for k in METRICS}
        arms={arm:{'mean':{k:statistics.mean(r[k] for r in runs.values()) for k in METRICS},'trajectory_values':runs,'trajectories_meeting_structural_target':sum(r['sheet_fraction']>=.25 and r['helix_fraction']<.4 for r in runs.values())} for arm,runs in by_arm.items()}
        differences={arm:contrast([{k:by_arm[arm][run][k]-by_arm[REFERENCE][run][k] for k in METRICS} for run in by_arm[REFERENCE]]) for arm in ARMS}
        interaction=contrast([{k:by_arm[ARMS[2]][run][k]-by_arm[ARMS[0]][run][k]-by_arm[ARMS[1]][run][k]+by_arm[REFERENCE][run][k] for k in METRICS} for run in by_arm[REFERENCE]])
        output[endpoint]=dict(arms=arms,paired_minus_reference=differences,factorial_interaction=interaction)
    return output


def markdown(result):
    lines=['# Seed-only coil intervention comparison','','Three new ten-trajectory arms plus the fixed, previously audited mixed control. Each trajectory has five optimized cycles. All means weight trajectories equally; cycle00 is initialization and excluded from the primary endpoint.','','| Arm | Sheet | Helix | Coil | Coil pLDDT <50 | Coil segments ≥16 | Binder pLDDT | iPTM |','|---|---:|---:|---:|---:|---:|---:|---:|']
    endpoint=result['endpoints']['optimized_cycles01_05']
    for arm,record in endpoint['arms'].items():
        m=record['mean'];lines.append(f"| {arm} | {m['sheet_fraction']:.1%} | {m['helix_fraction']:.1%} | {m['coil_fraction']:.1%} | {m['coil_confidence_below50_fraction']:.1%} | {m['coil_length_16+_fraction']:.1%} | {100*m['binder_plddt']:.1f} | {m['iptm']:.3f} |")
    lines+=['','All coil fractions use all binder residues as denominator. P-SEA coil includes ordered loops/turns; pLDDT cutoffs do not establish disorder.','','| Paired contrast | Sheet change, pp (95% CI) | Coil change, pp (95% CI) | Low-confidence coil change, pp (95% CI) |','|---|---:|---:|---:|']
    for name,record in [*endpoint['paired_minus_reference'].items(),('Factorial interaction',endpoint['factorial_interaction'])]:
        cells=[]
        for k in ('sheet_fraction','coil_fraction','coil_confidence_below50_fraction'):
            d=record[k];lo,hi=d['paired_bootstrap_95_ci'];cells.append(f"{100*d['mean_difference']:+.1f} ({100*lo:+.1f}, {100*hi:+.1f})")
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines+=['','Interaction = combined intervention − reduced-turn only − milder-anti only + original mixed control. Intervals use 20,000 paired trajectory bootstraps, are exploratory and unadjusted for multiple comparisons.','','## Limits','',*['- '+x for x in result['limitations']],'']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'Validation/output/secondary_structure_coil_v1/seed_trials')
    parser.add_argument('--reference-root',type=Path,default=ROOT/'Validation/output/secondary_structure_seed_mask_v1')
    args=parser.parse_args()
    reference=read_source(args.reference_root.resolve(),(REFERENCE,));intervention=read_source(args.root.resolve(),ARMS)
    validate_pairing(reference,intervention)
    result=dict(schema=1,operational_passed=True,method={'unit':'10 paired trajectory means across cycles01–05; cycle05 and initialization cycle00 separately','reference':'Previously completed mixed seed-only, anti0.5 turn0.5; exact scientific code/weights/seeds/grammar/mask checked','factorial_interaction':'combined minus low-turn minus mild-anti plus reference','bootstrap_replicates':prior.BOOTSTRAP_REPLICATES,'bootstrap_seed':prior.BOOTSTRAP_SEED},input_sha256={'reference':reference['input_sha256'],'intervention':intervention['input_sha256']},endpoints=build_summary(reference['rows']+intervention['rows']),scientific_decision=intervention['report'].get('decision_rule_evaluation'),limitations=['One target/configuration with ten matched seeds; no general natural-protein reference distribution is established.','The original control was completed earlier; smoke trajectory001 repeats the full seed and is counted once.','Confidence is prediction-model confidence, not physical stability or experimentally established disorder.','No best-cycle selection, no independent post-prediction checks, no binding validation, and no default promotion.','The local cycle00 retry intervention is a separate experiment and is not evaluated here.'])
    output=args.root/'analysis/full';output.mkdir(parents=True,exist_ok=True)
    (output/'comparison.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    (output/'comparison.md').write_text(markdown(result))
    print(json.dumps({'comparison':str(output/'comparison.md'),'operational_passed':True},indent=2))

if __name__=='__main__':
    main()
