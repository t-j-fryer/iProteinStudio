"""Read-only comparison of recorded timings; no inference or causal benchmark."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(os.environ['NANOHUNTER_ROOT'])
    hashes = {}
    def read(path):
        data = path.read_bytes(); hashes[str(path)] = hashlib.sha256(data).hexdigest()
        return json.loads(data)
    table = REPO/'Validation/output/bgx_completed_overviews_v1/timing.csv'
    hashes[str(table)] = hashlib.sha256(table.read_bytes()).hexdigest()
    historical = []
    for row in csv.DictReader(table.open()):
        if row['engine'] != 'boltz' or row['kind'] != 'minibinder':
            continue
        campaign = root/'projects/untitled_design'/row['campaign']
        configs = list((campaign/'_cycle_wave/resident_sessions').glob('*/config.json'))
        assert len(configs) == 1
        cfg = read(configs[0])
        responses = [read(p) for p in sorted(configs[0].parent.glob('responses/*.json'))]
        assert len(responses) == 6 and all(r['ok'] and r['completed_jobs']==50 for r in responses)
        seconds = sum(r['wall_seconds'] for r in responses)
        historical.append(dict(campaign=row['campaign'], condition=row['condition'],
            plotted_seconds_per_design=float(row['seconds_per_design']),
            resident_request_seconds_per_prediction=seconds/sum(r['completed_jobs'] for r in responses),
            predictions=sum(r['completed_jobs'] for r in responses),
            inputs_per_request=50, use_potentials=cfg['use_potentials'],
            model_load_counts=sorted(set(r['model_load_count'] for r in responses))))
    current = read(REPO/'lab_book/artifacts/0148-launch-biotin-without-noising/progress-20260917T2047.json')
    campaign = root/'projects/test2/nise_runs/nise-7345aaf6c30d1a9e'
    cfg = read(next((campaign/'sessions').glob('*/config.json')))
    assert current['completed']==12 and current['model_load_counts']==[1]
    assert all(r['phase']=='structure' for r in current['timings'])
    result = dict(hardware='Apple M4 Max / 64 GB; historical and current local records',
        historical=historical,
        current=dict(observed_at=current['observed_at'], predictions=current['completed'],
            resident_request_seconds_per_prediction=current['mean_prediction_seconds'],
            use_potentials=cfg['use_potentials'],inputs_per_request=1,
            phases=sorted(set(r['phase'] for r in current['timings'])),model_load_counts=[1]),
        limitations=['Different targets, sequences, MSA, seeds and sampling policies',
            'Historical model-byte equivalence not established',
            'Figure includes initialization/MPNN span per optimized output; request timings exclude MPNN',
            'No paired potential-on/off experiment; overhead contributions not isolated'],
        source_sha256=hashes)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},indent=2))


if __name__=='__main__':
    main()
