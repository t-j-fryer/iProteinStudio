"""Exercise the production sessions/launchers with no scientific mock models."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    root, cfgpath, engine, output = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    cfg = json.loads(cfgpath.read_text())
    sys.path.insert(0, str(root / 'scripts'))
    from prediction_profiles import activate, profile
    activate({})
    canonical = 'intellifold' if engine == 'intellifold-full' else engine
    model = {'intellifold': 'v2-flash', 'intellifold-full': 'v2', 'protenix-v2': 'v2',
             'protenix-mini': 'mini', 'protenix-constraint-v0.5': 'constraint'}.get(engine)
    configuration = dict(root=str(root), engine=canonical, model=model, seed='42', samples=1,
                         engine_args=['--num_workers', '0', '--output_format', 'mmcif'],
                         use_potentials=False, use_msa=True)
    t = time.perf_counter()
    session = None
    if engine != 'openfold-3-mlx' and cfg.get('route') != 'standalone':
        from resident_predictor import make_session
        session = make_session(configuration)
    load_seconds = time.perf_counter() - t
    timings, files = [], {}
    import yaml
    from validate_prediction_geometry import read_cif, cif_atom_rows, inspect_geometry
    aa = dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(), 'ARNDCQEGHILKMFPSTWYV'))
    for i, row in enumerate(cfg['rows']):
        unit = output / f'request_{i:02d}'
        source = unit / 'inputs'; source.mkdir(parents=True, exist_ok=True)
        inp = source / 'complex.yaml'
        msa = 'empty' if engine == 'esmfold2-fast-mlx' else cfg['msa']
        inp.write_text(yaml.safe_dump(dict(version=1, sequences=[
            dict(protein=dict(id='A', sequence=row['binder_sequence'], msa='empty')),
            dict(protein=dict(id='B', sequence=cfg['sequence'], msa=msa))]), sort_keys=False))
        prediction = unit / 'prediction'; prediction.mkdir(exist_ok=True)
        started = time.perf_counter()
        if cfg.get('route') == 'standalone':
            if engine == 'boltz':
                command = [sys.executable, str(root / 'scripts/boltz_mps.py'), 'predict', str(inp),
                           '--out_dir', str(prediction), '--cache', str(root / 'models/boltz2'),
                           '--num_workers', '0', '--diffusion_samples', '1', '--seed', '42']
            else:
                command = [sys.executable, str(root / 'scripts/protenix_predict.py'), '--yaml', str(inp),
                           '--output', str(prediction), '--nanohunter-root', str(root),
                           '--model', model, '--samples', '1', '--seeds', '42']
            subprocess.run(command, check=True)
        elif session:
            session.predict(source, prediction, 1)
        else:
            subprocess.run([sys.executable, str(root / 'rfd3_overlay/scripts/openfold_predict_one.py'),
                            '--yaml', str(inp), '--output', str(prediction), '--nanohunter-root', str(root)], check=True)
        timings.append(time.perf_counter() - started)
        structures = [p for p in prediction.rglob('*.cif') if '_profile_inputs' not in p.parts]
        assert structures, 'Missing structures'
        for structure in structures:
            columns, atoms = cif_atom_rows(structure)
            lookup = {n.removeprefix('_atom_site.'): j for j, n in enumerate(columns)}
            observed = {}
            import math
            for atom in atoms:
                assert all(math.isfinite(float(atom[lookup[k]])) for k in ('Cartn_x', 'Cartn_y', 'Cartn_z'))
                if atom[lookup['label_atom_id']] == 'CA':
                    observed.setdefault(atom[lookup['label_asym_id']], []).append(aa[atom[lookup['label_comp_id']]])
            assert {c: ''.join(v) for c, v in observed.items()} == {'A': row['binder_sequence'], 'B': cfg['sequence']}
            report = inspect_geometry(structure)
            assert not report['errors'], report
        confidence = [p for p in prediction.rglob('*.json') if any(k in p.name for k in ('confidence', 'summary'))]
        assert confidence, 'Missing confidence output'
        for path in structures + confidence + list(prediction.rglob('prediction_profile.json')):
            files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    if session and hasattr(session, 'residency'): session.residency.close()
    if session and hasattr(session, 'chemical_cache'): session.chemical_cache.close()
    if session and hasattr(session, 'session') and hasattr(session.session, 'close'): session.session.close()
    (output / 'complete.json').write_text(json.dumps(dict(engine=engine, settings=profile(canonical, model),
        model_load_count=getattr(session, 'model_load_count', None), load_seconds=load_seconds,
        request_seconds=timings, files=files), indent=2) + '\n')


if __name__ == '__main__': main()
