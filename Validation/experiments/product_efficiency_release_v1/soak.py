"""Managed, bounded CPU residency/restart check using the shipping wrapper."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main(config_path):
    cfg = json.loads(Path(config_path).read_text())
    out = Path(cfg['output']); scripts = Path(cfg['scripts']); root = Path(cfg['root'])
    python = root/'venvs/NanoHunter_lasermpnn/bin/python'
    prepared = out/'prepared.pdb'
    subprocess.run([str(python), str(scripts/'lasermpnn_prepare_input.py'), '--in-pdb', cfg['inputs'][0],
                    '--out-pdb', str(prepared), '--smiles', cfg['smiles'], '--designed-positions', 'all'], check=True)
    wrapper = scripts/'run_lasermpnn_seeded.py'
    queue = out/'worker'
    def command(destination, count=2, resident=True):
        return [str(python), str(wrapper), *(['--resident', str(queue), str(os.getpid())] if resident else []),
                '734', str(prepared), str(destination), str(count), '--device', 'cpu',
                '--model_weights_path', str(root/'src/LASErMPNN/model_weights/laser_weights_0p1A_nothing_heldout.pt'),
                '--sequence_temp', '.5', '--first_shell_sequence_temp', '.7', '--fs_calc_ca_distance', '10',
                '--disabled_residues', 'X,C', '--output_fasta_only', '--silent', '-c', '--ala_budget', '2', '--gly_budget', '0']
    def sample(name, resident=True):
        destination = out/name; destination.mkdir(exist_ok=True)
        with (destination/'run.log').open('w') as log:
            subprocess.run(command(destination, resident=resident), stdout=log, stderr=subprocess.STDOUT, check=True,
                           cwd=root/'src', timeout=180)
        return (destination/'designs.fasta').read_bytes()
    expected = sample('fresh', False)
    samples = []
    for i in range(64):
        assert sample(f'warm-{i:03d}') == expected, 'Warm/cold sequences or scores differ'
        state = json.loads((queue/'ready.json').read_text())
        rss = int(subprocess.check_output(['/bin/ps','-o','rss=','-p',str(state['pid'])], text=True).strip())
        samples.append(dict(request=i, pid=state['pid'], rss_kib=rss))
    # Interrupt only this test's CPU worker during a deliberately longer request.
    interrupted=out/'interrupted';interrupted.mkdir()
    session=Path(state['session']);before=len(list(session.glob('request-*.json')))
    with (interrupted/'run.log').open('w') as log:
        child=subprocess.Popen(command(interrupted,128), stdout=log, stderr=subprocess.STDOUT, cwd=root/'src')
        deadline=time.monotonic()+15
        while len(list(session.glob('request-*.json')))<=before and time.monotonic()<deadline:time.sleep(.05)
        os.kill(state['pid'], signal.SIGTERM)
        rc=child.wait(timeout=30)
        assert rc != 0, 'Interrupted request unexpectedly reported success'
    assert sample('after-worker-restart') == expected
    restarted=json.loads((queue/'ready.json').read_text())
    assert restarted['pid'] != state['pid']
    (Path(restarted['session'])/'STOP').touch()
    warm=[x['rss_kib'] for x in samples[16:]]
    growth=max(warm[-8:])-min(warm[:8])
    result=dict(passed=growth<128*1024, requests=64, sequences=128, exact_matches=64,
                rss_samples=samples, late_rss_growth_kib=growth, memory_limit_kib=128*1024,
                interrupted_request_failed=True, fresh_worker_restart_equal=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['passed'], 'Resident memory growth exceeded the declared 128 MiB bound'


if __name__=='__main__':main(sys.argv[1])
