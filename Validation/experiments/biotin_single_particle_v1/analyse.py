"""Audit guided one-particle replays and retrospectively assess exposure gates.

Never terminates inference. Snapshot exposure uses the unchanged production
filter and native Boltz atom ordering/writer, checked against the final PDB.
"""
import argparse
import csv
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import pickle
import re
import statistics
import sys


def read(path):
    return json.loads(path.read_text())


def exposure_policies(traces):
    """Fixed-step decisions and prospective-in-time persistence replay."""
    steps = traces[0]['steps']
    assert all(t['steps'] == steps for t in traces)
    fixed = []
    for j, step in enumerate(steps):
        rejected = [t for t in traces if not t['passes'][j]]
        fixed.append(dict(step=step,
            final_failures_caught=sum(not t['final_pass'] for t in rejected),
            false_rejections=[t['id'] for t in rejected if t['final_pass']],
            final_failures_missed=sum(not t['final_pass'] and t['passes'][j] for t in traces)))
    policies = []
    for start in (25, 50, 75, 100, 125, 150, 175):
        for consecutive in (1, 2, 3):
            decisions = []
            for t in traces:
                failures = 0
                for j, step in enumerate(steps):
                    if step < start or step == 200:
                        continue
                    failures = failures + 1 if not t['passes'][j] else 0
                    if failures >= consecutive:
                        decisions.append(dict(id=t['id'], step=step, false_rejection=t['final_pass'],
                            remaining_steps=200-step,
                            gross_remaining_traced_seconds=max(0., t['total_seconds']-t['elapsed_seconds'][j])))
                        break
            policies.append(dict(start_step=start, consecutive_checks=consecutive,
                caught_final_failures=sum(not d['false_rejection'] for d in decisions),
                false_rejections=[d['id'] for d in decisions if d['false_rejection']],
                decisions=decisions,
                hypothetical_remaining_step_fraction=sum(d['remaining_steps'] for d in decisions)/(200*len(traces)),
                gross_remaining_traced_time_fraction=sum(d['gross_remaining_traced_seconds'] for d in decisions)/sum(t['total_seconds'] for t in traces)))
    return dict(fixed_step=fixed, persistence=policies,
        final_pass_count=sum(t['final_pass'] for t in traces),
        final_fail_count=sum(not t['final_pass'] for t in traces),
        warning='Retrospective, in-sample; remaining steps are not measured wall-time savings. Filter overhead and independent validation absent.')


def analyse(output, destination, baseline):
    import gemmi
    import numpy as np
    import yaml
    scripts = output / '.studio_runtime/pipeline/scripts'
    sys.path[:0] = [str(scripts), str(scripts / 'nise')]
    from runtime import Journal, Backend
    from nise_lib import self_consistency
    from atom_geometry import measure
    from boltz_replay_validation import validate, checksum
    from boltz.data.types import StructureV2, Coords, Interface
    from boltz.data.write.pdb import to_pdb
    spec = importlib.util.spec_from_file_location('prior_analysis', Path(__file__).parents[1] / 'biotin_guidance_replay_v1/analyse.py')
    prior = importlib.util.module_from_spec(spec); spec.loader.exec_module(prior)
    config = read(output / 'replay_config.json'); validate(output, config)
    ids = config['ids']; journal = Journal(output)
    settings = read(output / 'inputs/nise_config.json')['request']
    manifest = read(output / 'inputs/ligand_atom_map.json')
    rows, raw, workers, summaries, pairing = [], [], {}, {}, []
    destination.mkdir(parents=True, exist_ok=True)
    def pdb(arm, name):
        return output / arm / 'all/out/boltz_results_yaml/predictions' / name / f'{name}_model_0.pdb'
    def coordinates(path):
        return {(c.name, str(r.seqid), a.name): np.array([a.pos.x,a.pos.y,a.pos.z])
                for c in gemmi.read_structure(str(path))[0] for r in c for a in r}
    for arm in ('physical', 'physical_trace'):
        path = output / arm / 'all/completed.json'; receipt = read(path)
        timing = journal.load(path, receipt['input'])
        if not timing or timing['completed_jobs'] != len(ids):
            raise ValueError('Missing or invalid atomic arm receipt')
        readies = [read(p) for p in (output / arm / 'sessions').glob('*/ready.json')]
        responses = [read(p) for p in (output / arm / 'sessions').glob('*/responses/*.json')]
        steering = [read(p) for p in (output / arm / 'sessions').glob('*/actual_steering.json')]
        if (len(readies) != 1 or readies[0]['device'] != 'mps' or readies[0]['fallback'] != 0
                or len(responses) != 1 or not responses[0]['ok'] or responses[0]['model_load_count'] != 1
                or len(steering) != 1 or steering[0]['effective_diffusion_particles'] != 1):
            raise ValueError('Not one complete MPS-resident request per arm')
        hparams = [yaml.safe_load(p.read_text()) for p in (output / arm).rglob('hparams.yaml')]
        if len(hparams) != 1:
            raise ValueError('Missing executed settings')
        for s in [steering[0], hparams[0]['steering_args']]:
            if s['fk_steering'] or not s['physical_guidance_update'] or not s['contact_guidance_update']:
                raise ValueError('Incorrect guidance settings')
        hp = hparams[0]['predict_args']
        if (hp['recycling_steps'],hp['sampling_steps'],hp['diffusion_samples']) != (3,200,1):
            raise ValueError('Changed diffusion/recycling budget')
        logs = '\n'.join(p.read_text() for p in (output / arm / 'sessions').glob('*/worker.log'))
        warnings = [l for l in logs.splitlines() if 'will fall back to run on the CPU' in l]
        if any('aten::linalg_svd' not in l for l in warnings):
            raise ValueError('Unexpected fallback')
        steps = re.findall(r'REPLAY\|replay\|(L\d+)\|([0-9.]+)', logs)
        if sorted(n for n,_ in steps) != ids or logs.count('IPROTEINSTUDIO_MPS_ALLOCATOR_RESET|boltz|') != len(ids):
            raise ValueError('Unexpected prediction cardinality')
        workers[arm] = dict(startup_seconds=readies[0]['startup_seconds'], requests=1, model_load_count=1,
            input_order=[name for name,_ in steps],
            actual_steering=steering[0], model_step_seconds={n:float(s) for n,s in steps},
            fallback_warnings=warnings, timing_receipt=timing)
        for name in ids:
            path = pdb(arm,name)
            seq = read(output / 'inputs' / name / 'completed.json')['input']['sequence']
            Backend.audit_structure(path,seq,True)
            if len(list(path.parent.glob('*.pdb'))) != 1 or len(list(path.parent.glob('confidence_*.json'))) != 1 or list(path.parent.glob('affinity_*.json')):
                raise ValueError('Invalid structure/confidence/affinity output cardinality')
            mols = pickle.loads((output / 'inputs' / name / 'processed/mols' / f'{name}.pkl').read_bytes())
            if len(mols) != 1:
                raise ValueError('Expected one ligand')
            g = prior.geometry(path, settings, manifest, next(iter(mols.values())))
            rows.append(dict(arm=arm,id=name,**g['metrics']))
            raw.append(dict(arm=arm,id=name,path=str(path),sha256=checksum(path),**g))
        selected = [r for r in rows if r['arm'] == arm]
        summaries[arm] = dict(count=len(ids), seconds_per_initialization=timing['wall_seconds']/len(ids),
            request_seconds=timing['wall_seconds'], startup_seconds=readies[0]['startup_seconds'],
            atom_pass_count=sum(r['atom_checks_passed'] for r in selected),
            exposure_pass_count=sum(r['exposed_passed'] for r in selected),
            correct_ligand_chirality_count=sum(r['ligand_chiral_errors']==0 for r in selected),
            no_severe_protein_ligand_overlap_count=sum(r['severe_protein_ligand_overlaps']==0 for r in selected),
            no_severe_nonlocal_protein_overlap_count=sum(r['severe_nonlocal_protein_overlaps']==0 for r in selected),
            valid_ligand_bonds_count=sum(r['ligand_bond_violations']==0 for r in selected),
            mean_ligand_plddt=statistics.mean(r['ligand_plddt'] for r in selected))
        summaries[arm]['atom_and_chirality_pass_count']=sum(r['atom_checks_passed'] and r['ligand_chiral_errors']==0 for r in selected)
    indexed = {(r['arm'],r['id']):r for r in rows}
    for name in ids:
        aligned = self_consistency(pdb('physical_trace',name),pdb('physical',name))
        pairing.append(dict(id=name, ca_rmsd=aligned.ca_rmsd, ligand_rmsd=aligned.ligand_rmsd,
            atom_filter_match=indexed['physical',name]['atom_checks_passed']==indexed['physical_trace',name]['atom_checks_passed'],
            exposure_filter_match=indexed['physical',name]['exposed_passed']==indexed['physical_trace',name]['exposed_passed'],
            chirality_match=indexed['physical',name]['ligand_chiral_errors']==indexed['physical_trace',name]['ligand_chiral_errors']))
    traces, trace_rows = [], []
    for name in ids:
        leaf = output / 'physical_trace/traces' / name
        meta = read(leaf / 'metadata.json')
        archive = np.load(leaf / 'coordinates.npz', allow_pickle=False)
        if archive['steps'].tolist() != config['trace_steps'] or not np.array_equal(archive['current'][-1],archive['final']):
            raise ValueError('Incomplete trace/final-coordinate mismatch')
        structure = StructureV2.load(output / 'inputs' / name / 'processed/structures' / f'{name}.npz').remove_invalid_chains()
        def emit(frame, path):
            coords = frame[0][archive['atom_mask']]
            if len(coords) != len(structure.atoms) or not np.isfinite(coords).all():
                raise ValueError('Invalid atom ordering or coordinates')
            atoms = structure.atoms.copy(); atoms['coords']=coords; atoms['is_present']=True
            residues = structure.residues.copy(); residues['is_present']=True
            st = replace(structure, atoms=atoms, residues=residues, interfaces=np.array([],dtype=Interface),
                         coords=np.array([(x,) for x in coords],dtype=Coords))
            path.write_text(to_pdb(st,plddts=None,boltz2=True))
        target = destination / 'snapshots' / name; target.mkdir(parents=True,exist_ok=True)
        final_path = target / 'final.pdb'; emit(archive['final'],final_path)
        a,b = coordinates(final_path),coordinates(pdb('physical_trace',name))
        if a.keys()!=b.keys() or any(not np.array_equal(a[k],b[k]) for k in a):
            raise ValueError('Native snapshot atom mapping differs from emitted final PDB')
        final_checks = measure(final_path,settings,manifest)
        final_pass = all(v['retained_fraction']>=settings['exposure_min_fraction'] for v in final_checks['exposure'].values())
        if final_pass != indexed['physical_trace',name]['exposed_passed']:
            raise ValueError('Final exposure mapping mismatch')
        trajectory = dict(id=name, steps=config['trace_steps'], final_pass=final_pass, passes=[], fractions=[],
            final_fractions={k:v['retained_fraction'] for k,v in final_checks['exposure'].items()},
            elapsed_seconds=meta['elapsed_seconds'],total_seconds=meta['total_prediction_seconds'],
            diffusion_started_seconds=meta['diffusion_started_seconds'],snapshot_callback_seconds=meta['snapshot_callback_seconds'])
        for j,step in enumerate(config['trace_steps']):
            # Early noisy coordinates span an enormous, nonphysical box and
            # FreeSASA's spatial grid can exhaust memory. They are archived,
            # but only the model's denoised estimate is a meaningful gate input.
            for state in ('denoised',):
                path=target/f'{state}_{step:03d}.pdb'; emit(archive[state][j],path)
                checks=measure(path,settings,manifest)
                fractions={k:v['retained_fraction'] for k,v in checks['exposure'].items()}
                passed=all(v>=settings['exposure_min_fraction'] for v in fractions.values())
                trace_rows.append(dict(id=name,step=step,state=state,exposure_pass=passed,
                    final_exposure_pass=final_pass,min_exposure=min(fractions.values()),
                    pocket_pass=all(d<=settings['hotspot_distance'] for d in checks['hotspot_distance_a'].values()),
                    **fractions))
                if state=='denoised':
                    trajectory['passes'].append(passed); trajectory['fractions'].append(fractions)
        traces.append(trajectory)
        print(f'Analysed {name}: final exposure={final_pass}',flush=True)
    old=read(baseline)
    for arm, summary in old['summary'].items():
        summary['atom_and_chirality_pass_count']=sum(r['atom_checks_passed'] and r['ligand_chiral_errors']==0 for r in old['rows'] if r['arm']==arm)
    if workers['physical']['input_order'] != workers['physical_trace']['input_order']:
        raise ValueError('Clean and traced requests changed input order')
    old_order=list(old['workers']['batch']['model_step_seconds'])
    if len(ids)==len(old_order) and workers['physical']['input_order']!=old_order:
        raise ValueError('Main replay input order differs from prior pocket-only batch')
    result=dict(audit_passed=True,output=str(output),count=len(ids),summary=summaries,workers=workers,
        analysis_provenance={str(p):checksum(p) for p in
            (Path(__file__).resolve(),Path(prior.__file__).resolve(),scripts/'nise/atom_geometry.py')},
        pairing=pairing,rows=rows,raw_metrics=raw,traces=traces,trace_rows=trace_rows,
        exposure_analysis=exposure_policies(traces),
        baseline=dict(path=str(baseline.resolve()),sha256=checksum(baseline),summary=old['summary']),
        limits='X-containing initial structures, one ligand, no affinity or binding validation. No live early termination. Single timing trial per arm on Apple M4 Max 64 GB. Original comparison includes preprocessing; replays use frozen preprocessing. Snapshots can perturb timing and numerical execution.')
    return result


def report(result,destination):
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    for key in ('rows','trace_rows'):
        with (destination/f'{key}.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(result[key][0]));writer.writeheader();writer.writerows(result[key])
    ea=result['exposure_analysis']; n=result['count']
    lines=['# Physical guidance without FK; early exposure audit','',
        f'{n} paired X-containing initial structures; Apple M4 Max, 64 GB. Each new arm is one all-input request to one loaded model. Data-loader batch size remains 1.','',
        '| Measure | Original physical + FK | Prior pocket-only batch | New physical, FK off |','|---|---:|---:|---:|']
    for label,key in [('Seconds / initialization','seconds_per_initialization'),('Pocket + exposure pass','atom_pass_count'),
        ('Pocket + exposure + correct chirality','atom_and_chirality_pass_count'),
        ('Correct ligand stereochemistry','correct_ligand_chirality_count'),('No severe protein–ligand overlaps','no_severe_protein_ligand_overlap_count'),
        ('No severe nonlocal protein overlaps','no_severe_nonlocal_protein_overlap_count'),('Ligand bond diagnostic pass','valid_ligand_bonds_count'),('Mean ligand pLDDT','mean_ligand_plddt')]:
        values=[result['baseline']['summary'][a][key] for a in ('original','batch')]+[result['summary']['physical'][key]]
        lines.append('| '+label+' | '+' | '.join(str(v) if isinstance(v,int) else f'{v:.2f}' for v in values)+' |')
    lines+=['','Only the untraced arm is a clean timing comparison. Startup is separate in audit.json. Physical guidance and force:true pocket guidance are active, FK is disabled, 3 recycles, 200 steps, seed0, one sample, empty MSA, no affinity. Identical frozen features/conformers and per-input random states are checked.','',
        f'Prior controls each contain {result["baseline"]["summary"]["original"]["count"]} initializations. New traced pass: {result["summary"]["physical_trace"]["seconds_per_initialization"]:.2f} s/initialization (instrumented, excluded from the speed comparison). Final exposure outcomes in traced arm: {ea["final_pass_count"]} pass, {ea["final_fail_count"]} fail. Snapshot atom mapping reproduces final PDB coordinates exactly.','',
        'Early exposure uses the corrected denoised estimate, not the still-noisy diffusion state. Both O18 and O19 must retain ≥50% of isolated-ligand SASA, using the unchanged production filter. Snapshots occur at step1 and every5 steps. Final labels use the emitted structure; the denoised estimate at step200 can still differ from the final integration update. Recycling has no complete coordinate output for this check.','',
        '| Fixed check at step | Final failures caught | Final passers incorrectly rejected |','|---|---:|---:|']
    for r in ea['fixed_step']:
        if r['step'] in (1,25,50,75,100,125,150,175,200):
            lines.append(f'| {r["step"]} | {r["final_failures_caught"]} | {len(r["false_rejections"])} |')
    lines+=['','## Persistence policies (retrospective)','',
        'Consecutive checks must fail after the chosen start step. Stop at the first qualifying check before step200; all results here are hypothetical, every prediction actually finished.','',
        '| Start | Consecutive checks | Failures caught | False rejections | Remaining diffusion-step fraction |','|---|---:|---:|---:|---:|']
    for r in ea['persistence']:
        lines.append(f'| {r["start_step"]} | {r["consecutive_checks"]} | {r["caught_final_failures"]} | {len(r["false_rejections"])} | {r["hypothetical_remaining_step_fraction"]:.1%} |')
    zero_false=[r for r in ea['persistence'] if not r['false_rejections'] and r['caught_final_failures']]
    if zero_false:
        best=max(zero_false,key=lambda r:r['hypothetical_remaining_step_fraction'])
        decisions=best['decisions']
        lines+=['',f'Among the tested rules with no observed false rejection, starting at step {best["start_step"]} and requiring {best["consecutive_checks"]} consecutive failed observations leaves the largest remaining-step budget. It catches {best["caught_final_failures"]}/{ea["final_fail_count"]} eventual failures, rejecting at steps {min(d["step"] for d in decisions)}–{max(d["step"] for d in decisions)}, while retaining all {ea["final_pass_count"]} eventual passers. The gross remaining traced prediction time is {best["gross_remaining_traced_time_fraction"]:.1%} of total traced model time; this is an optimistic opportunity estimate, before live filtering costs, not a measured speedup. The rule was selected on this same small sample.']
    lines+=['','The remaining-step fraction is a gross opportunity estimate, not measured speedup: it includes falsely rejected candidates where present, diffusion steps have unequal costs, recycling has already run, and live filter overhead is unmeasured. Choosing a threshold on these same inputs is exploratory. Zero observed false rejections in this small sample does not establish a safe production gate.','',
        f'Clean/traced exposure verdict mismatches: {sum(not p["exposure_filter_match"] for p in result["pairing"])}/{n}. Maximum aligned Cα difference: {max(p["ca_rmsd"] for p in result["pairing"]):.4f} Å; maximum ligand RMSD under the same protein alignment: {max(p["ligand_rmsd"] for p in result["pairing"]):.4f} Å. Identical random-state restoration on MPS does not imply bitwise-identical predictions.','',result['limits'],'',
        'No production defaults changed; the original campaign remains paused. Raw receipts, feature and source hashes, snapshots, geometry metrics and per-input decisions are retained.',
        '', '[Overview figure](overview.svg) · [Per-snapshot metrics](trace_rows.csv) · [Full audit](audit.json)']
    (destination/'REPORT.md').write_text('\n'.join(lines)+'\n')


def plot(result,destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'Arial','text.color':'black','axes.labelcolor':'black',
        'xtick.direction':'in','ytick.direction':'in','axes.grid':False,'svg.fonttype':'none'})
    traces=result['traces']; ea=result['exposure_analysis']; n=result['count']
    fig,axs=plt.subplots(2,2,figsize=(14,10))
    a=axs[0,0]
    values=[result['baseline']['summary'][k]['seconds_per_initialization'] for k in ('original','batch')]
    values.append(result['summary']['physical']['seconds_per_initialization'])
    a.bar(range(3),values,color=['#8e9baf','#e7b26d','#6db6a8'],edgecolor='black')
    a.set_xticks(range(3),['Physical + FK\nprior singleton','Pocket only\nprior one request','Physical, no FK\nnew one request'])
    a.set_ylabel('Seconds per initial structure (startup excluded)')
    for j,v in enumerate(values):a.text(j,v,f'{v:.1f}',ha='center',va='bottom')
    a.set_ylim(0,max(values)*1.18)
    a=axs[0,1]
    ss=[result['baseline']['summary'][k] for k in ('original','batch')]+[result['summary']['physical']]
    for j,key in enumerate(('atom_pass_count','correct_ligand_chirality_count','no_severe_nonlocal_protein_overlap_count')):
        a.bar(np.arange(3)+(j-1)*.25,[s[key] for s in ss],width=.25,edgecolor='black',
            label=['Pocket + exposure','Correct chirality','No severe internal protein overlap'][j])
    a.set_xticks(range(3),['Physical + FK','Pocket only','Physical, no FK']);a.set_ylabel('Passing initial structures');a.legend(fontsize=8)
    a.set_ylim(0,max(s['count'] for s in ss)*1.22)
    a=axs[1,0]
    data=np.array([[min(f.values()) for f in t['fractions']] for t in traces])
    im=a.imshow(data,aspect='auto',vmin=0,vmax=1,cmap='viridis',interpolation='nearest')
    indices=[i for i,s in enumerate(traces[0]['steps']) if s in (1,25,50,75,100,125,150,175,200)]
    a.set_xticks(indices,[traces[0]['steps'][i] for i in indices]);a.set_xlabel('Diffusion step (corrected denoised estimate)')
    a.set_yticks(range(n),[t['id']+(' +' if t['final_pass'] else '') for t in traces],fontsize=7)
    a.set_ylabel('Input; + = final exposure pass');fig.colorbar(im,ax=a,label='Minimum O18/O19 retained SASA (pass ≥0.5)')
    a=axs[1,1]
    a.plot([r['step'] for r in ea['fixed_step']],[r['final_failures_caught'] for r in ea['fixed_step']],label='Final failures caught',color='#17806c')
    a.plot([r['step'] for r in ea['fixed_step']],[len(r['false_rejections']) for r in ea['fixed_step']],label='Final passers wrongly rejected',color='#be442a')
    a.set_xlabel('Single exposure check at diffusion step');a.set_ylabel('Initial structures');a.set_ylim(0,n);a.legend(fontsize=9)
    fig.suptitle('Biotin: physical guidance without FK and exposure during diffusion')
    fig.text(.5,.015,f'New paired unit: n={n} X-containing initial structures; prior controls n=30. Apple M4 Max, 64 GB. No early kills.\nOriginal timing includes preprocessing; replays freeze it. Snapshot timings excluded from speed comparison. Exploratory, one timing trial.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,.96));fig.savefig(destination/'overview.svg',transparent=True);fig.savefig(destination/'overview.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=Path('Validation/output/biotin_guidance_replay_v1/main/analysis/audit.json'))
    p.add_argument('--plot-audit',type=Path);args=p.parse_args()
    if args.plot_audit:plot(read(args.plot_audit),args.destination)
    else:report(analyse(args.output,args.destination,args.baseline),args.destination)
