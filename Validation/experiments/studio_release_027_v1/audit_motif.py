"""Audit the bounded release pilot; never change its raw scientific outputs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'Sources/iProteinStudio/Resources/pipeline/scripts'))
from motif_beta.contract import verify
from motif_beta.geometry import read, evaluate, LETTERS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for item in value.values(): finite(item)
    elif isinstance(value, list):
        for item in value: finite(item)


def same(left, right):
    if isinstance(left, float) and isinstance(right, float):
        assert math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)
    elif isinstance(left, dict):
        assert set(left) == set(right)
        for key in left: same(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right): same(a, b)
    else:
        assert left == right


def audit(run, interruption, job):
    saved = verify(run / 'bundle')
    assert saved['request']['case_id'] == 'M0349_1e3v'
    assert saved['request']['roots'] == saved['request']['cycles'] == 1
    result = json.loads((run / 'comparison_results.json').read_text())
    assert result['attempted_sequences'] == result['checked'] == 2
    assert result['failures'] == []
    assert result['independent_family_validation'] is False
    refs = json.loads((run / 'roots.json').read_text())
    assert len(refs) == 1
    reference = Path(refs[0]['reference'])
    ref = json.loads(reference.read_text())
    assert ref['root_sha256'] == sha(Path(refs[0]['backbone']))
    assert ref['bundle_sha256'] == sha(run / 'bundle/bundle.json')
    records, files = [], {}
    for receipt in run.glob('cycles/**/complete.json'):
        d = json.loads(receipt.read_text())
        for name, expected in d['files'].items():
            path = receipt.parent / name
            assert sha(path) == expected, path
            files[str(path.relative_to(run))] = expected
        if receipt.parent.name not in {'guided', 'untemplated'}: continue
        for name, document in d['input']['documents'].items():
            path = Path(d['result'][name])
            residues = read(path)  # finite, unique heavy atoms; exactly one model
            sequence = ''.join(LETTERS[r['component']] for k, r in residues.items() if k.startswith('A:'))
            expected = document['sequences'][0]['protein']['sequence']
            assert sequence == expected and len(sequence) == 128
            assert all({'N', 'CA', 'C', 'O'} <= set(residue['atoms'])
                       for key, residue in residues.items() if key.startswith('A:'))
            assert document['sequences'][0]['protein']['msa'] == 'empty'
            assert bool(document.get('templates')) == (receipt.parent.name == 'guided')
            assert set(residues) == set(ref['atoms'])
            for key, component in ref['identities'].items():
                assert residues[key]['component'] == component
            for ligand in ref['ligands']:
                observed = residues[ligand['key']]
                assert observed['component'] == ligand['component']
                assert set(observed['atoms']) == set(ligand['atoms'])
                assert all(observed['atoms'][atom]['element'] == ref['atoms'][ligand['key']]['atoms'][atom]['element']
                           for atom in ligand['atoms'])
            identity = json.loads(path.with_suffix('.identity.json').read_text())
            native = path.with_name(path.stem.removesuffix('_mapped') + '.pdb')
            assert identity['native_sha256'] == sha(native)
            assert identity['mapped_sha256'] == sha(path)
            submitted = {entry['ligand']['id']: entry['ligand']['ccd']
                         for entry in document['sequences'] if 'ligand' in entry}
            assert {entry['chain']: entry['ccd'] for entry in identity['entities']} == submitted
            confidence = path.with_name('confidence_' + path.stem.removesuffix('_mapped') + '.json')
            confidence_values = json.loads(confidence.read_text())
            finite(confidence_values)
            assert 0 <= confidence_values['confidence_score'] <= 1
            files[str(confidence.relative_to(run))] = sha(confidence)
            plddt = [r['atoms']['CA']['b'] for k, r in residues.items() if k.startswith('A:')]
            assert all(0 <= value <= 100 for value in plddt)
            records.append(dict(designer=receipt.parents[2].name, role=receipt.parent.name,
                                length=len(sequence), structure=str(path.relative_to(run))))
    assert len(records) == 4
    for candidate in result['candidates']:
        metrics = candidate['metrics']
        recomputed = evaluate(reference, candidate['checked_structure'], metrics['protein_plddt'])
        same(recomputed, metrics)
    sessions, responses = [], []
    for ready_path in run.glob('sessions/*/ready.json'):
        ready = json.loads(ready_path.read_text())
        assert ready['device'] == 'mps' and ready['fallback'] == 0 and ready['model_load_count'] == 1
        assert ready['config_sha256'] == sha(ready_path.parent / 'config.json')
        sessions.append(ready_path.parent.name)
        for path in ready_path.parent.glob('responses/*.json'):
            d = json.loads(path.read_text())
            assert d['ok'] and d['completed_jobs'] == d['model_load_count'] == 1
            responses.append(d['request_id'])
    assert len(sessions) == 2 and len(set(responses)) == 4
    interrupted = json.loads(interruption.read_text())
    for name, previous in interrupted['completed_files'].items():
        path = run / name
        assert sha(path) == previous['sha256'] and path.stat().st_mtime_ns == previous['mtime_ns'], name
    summaries = [json.loads(path.read_text()) for path in (job / 'memory').glob('*.summary.json')]
    assert summaries, 'Managed memory summaries missing'
    return dict(technical_pass=True, case='M0349_1e3v', roots=1, proposals=2,
                predictions=records, resident_sessions=len(sessions), completed_requests=len(responses),
                loads_per_session=1, mps_fallback=0, replayed_files=len(interrupted['completed_files']),
                quality_passes=result['passed'], independent_family_validation=False,
                experimental_validation=False, memory_summaries=summaries, audited_files=files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--interruption', type=Path, required=True)
    parser.add_argument('--job-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run, args.interruption, args.job_directory)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'audited_files', 'memory_summaries'}}))
