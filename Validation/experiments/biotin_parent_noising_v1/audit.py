"""Audit immutable branch-test outputs without running inference."""
import argparse
import json
import math
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def audit(output):
    sys.path.insert(0, str(output / '.studio_runtime/pipeline/scripts/nise'))
    from runtime import Journal, Backend
    from atom_geometry import measure
    import nise_lib
    settings = read(output / 'nise_config.json')['request']
    manifest = read(output / 'ligand_atom_map.json')
    journal = Journal(output)
    receipt_count = 0
    for path in output.rglob('*.json'):
        if '.studio_runtime' in path.parts:
            continue
        row = read(path)
        if isinstance(row, dict) and {'input', 'result', 'files'} <= row.keys():
            journal.load(path, row['input']); receipt_count += 1
    parent = read(output / 'parent_audit.json')
    assert parent['self_consistency_passed'] and parent['atom_checks_passed']
    selection = read(output / 'cycle02/partial_noising/selection.json')['trajectories']['0']
    masks = read(output / 'cycle02/partial_noising/T0/masks.json')['result']
    original = read(output / 'branch_test_inputs/parent.json')['sequence']
    for proposal in masks['proposals']:
        changed = [i+1 for i, (a,b) in enumerate(zip(original, proposal['sequence'])) if a != b]
        assert changed == proposal['masked_positions']
        assert set(changed) <= set(masks['eligible_positions'])
        assert all(proposal['sequence'][i-1] == 'X' for i in changed)
    candidates = [read(p) for p in sorted((output / 'candidates').glob('*.json'))]
    rows = []
    for c in candidates:
        pdb = output / c['pdb']
        Backend.audit_structure(pdb, c['sequence'], True)
        atoms = measure(pdb, settings, manifest)
        assert atoms['passed'] == c['atom_checks']['passed']
        sc = nise_lib.self_consistency(str(pdb), str(output / c['ref_pdb']), ca_thresh=settings['nise_sc_ca'], lig_thresh=float('inf'))
        assert (sc.ok and atoms['passed']) == c['geometry_passed']
        if c['branch'] == 'masked-backbone':
            assert not c['passed'] and not c['final_eligible']
        if c['pbind'] is not None:
            assert c['geometry_passed'], 'Affinity ran on a geometry-failing candidate'
            assert math.isclose(c['score'], c['pbind'] + c['ligand_plddt']/100, abs_tol=1e-8)
        comparison = nise_lib.self_consistency(str(pdb), str(output / 'branch_test_inputs/parent.pdb'),
            ca_thresh=settings['nise_sc_ca'], lig_thresh=settings['nise_sc_lig'])
        rows.append({**{k:c[k] for k in ('name','branch','score','pbind','ligand_plddt','ca_rmsd','ligand_rmsd','geometry_passed','score_status')},
            'would_pass_cycle3_geometry': bool(sc.ca_rmsd < settings['nise_sc_ca'] and
                                              sc.ligand_rmsd < settings['nise_sc_lig'] and atoms['passed']),
            'ca_rmsd_vs_original_parent': comparison.ca_rmsd,
            'ligand_rmsd_vs_original_parent': comparison.ligand_rmsd,
            'atom_failures': atoms['failures']})
    readies = [read(p) for p in (output / 'sessions').glob('*/ready.json')]
    assert len(readies)==1 and readies[0]['device']=='mps' and readies[0]['fallback']==0
    responses = [read(p) for p in (output / 'sessions').glob('*/responses/*.json')]
    assert responses and all(r['ok'] and r['model_load_count'] in (1,2) for r in responses)
    log = '\n'.join(p.read_text() for p in (output / 'sessions').glob('*/worker.log'))
    fallbacks = [line for line in log.splitlines() if 'will fall back to run on the CPU' in line]
    assert all('aten::linalg_svd' in line for line in fallbacks)
    fold_receipts = [read(p) for p in (output / 'cycle02').rglob('completed.json')]
    sessions = {r['result']['timing']['session'] for r in fold_receipts}
    assert len(sessions)==1
    repairs = [c for c in candidates if c['branch']=='partial-noising-repair']
    accepted = bool(selection['advanced']) and len(repairs)==settings['noise_mpnn_seqs']
    if accepted:
        assert any(r.get('phase')=='affinity' and r['model_load_count']==2 for r in responses)
        for name in selection['advanced']:
            c = next(c for c in candidates if c['name']==name)
            assert c['final_eligible'] and c['passed'] and c['geometry_passed']
            assert set(c['sequence']) <= set('ACDEFGHIKLMNPQRSTVWY')
    return dict(accepted=accepted, branch_status=selection['status'], selected=selection['advanced'],
        eligible_residues=len(masks['eligible_positions']), masked_residues=masks['masked_count'],
        structure_evaluations=len(fold_receipts), affinity_evaluations=len(list((output/'cycle02').rglob('affinity_completed.json'))),
        audited_operation_receipts=receipt_count, resident_pid=readies[0]['pid'], resident_sessions=len(sessions),
        documented_svd_fallback_warnings=len(fallbacks), candidates=rows,
        limitation='One parent, two masks and three repairs; no efficacy, throughput or full-campaign claim')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=audit(args.output)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
