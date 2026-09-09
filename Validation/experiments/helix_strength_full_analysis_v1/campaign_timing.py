"""Descriptive elapsed time per optimized output, from audited trajectory timers.

A resident/cycle-wave cohort's timers overlap: count its elapsed span once.
These historical native-setting campaigns are not controlled speed benchmarks.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

DEFINITION = ('Seconds per optimized design = summed pilot and remaining design-stage spans / 50 '
              'completed cycle01–05 outputs (10 trajectories × 5 cycles). Each phase span is '
              'latest trajectory end minus earliest trajectory start; overlapping resident-worker '
              'timers are counted once. Includes initialization, MPNN and gaps within the recorded '
              'span; excludes queueing and setup before the first trajectory timer. This is '
              'amortized elapsed time, not individual prediction latency. One aggregate per '
              'condition from two unequal phases (1 + 9 trajectories); no timing CI. '
              'Apple M4 Max, 64 GB, macOS 26.6.1; native settings differ across engines, '
              'so these are descriptive campaign costs, not a controlled engine speed comparison.')


def phase_span(rows):
    if not rows:
        raise ValueError('Missing trajectory timings')
    starts, ends = [], []
    names = set()
    for row in rows:
        start, end, duration = (float(row[k]) for k in ('start_ts', 'end_ts', 'duration_sec'))
        if (not all(math.isfinite(v) for v in (start, end, duration)) or end <= start
                or duration <= 0 or abs(end-start-duration) > 1e-5):
            raise ValueError('Invalid or inconsistent trajectory duration')
        if row['run'] in names:
            raise ValueError('Duplicate trajectory timing')
        names.add(row['run']); starts.append(start); ends.append(end)
    return max(ends) - min(starts)


def summarize(study, engines, suffixes):
    study = Path(study)
    arms, sources = {}, {}
    for engine in engines:
        for suffix in suffixes:
            arm = engine + '_h' + suffix
            phases = {}; completed = 0
            for phase, count in [('pilot', 1), ('remaining', 9)]:
                audit = json.loads((study/'audits'/phase/(arm+'.json')).read_text())
                rows = []
                for name, expected in audit['raw_sha256'].items():
                    if not name.endswith('/timing_run.csv'):
                        continue
                    path = (study/name).resolve()
                    if study.resolve() not in path.parents:
                        raise ValueError('Timing file is outside the study')
                    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                    if checksum != expected:
                        raise ValueError('Audited timing file changed: '+name)
                    sources[name] = checksum
                    with path.open(newline='') as stream:
                        values = list(csv.DictReader(stream))
                    if len(values) != 1:
                        raise ValueError('Expected one timing row per trajectory')
                    rows += values
                trajectories = audit['trajectories']
                if len(rows) != count or len(trajectories) != count or any(
                        t['outcome'] != 'completed' or t['completed_cycles'] != 5 for t in trajectories):
                    raise ValueError('Timing cardinality differs from completed designs')
                phases[phase] = phase_span(rows)
                completed += sum(t['completed_cycles'] for t in trajectories)
            arms[arm] = dict(phase_seconds=phases, recorded_span_seconds=sum(phases.values()),
                             optimized_designs=completed, trajectories=10,
                             seconds_per_design=sum(phases.values())/completed)
    return dict(definition=DEFINITION, arms=arms, source_sha256=sources)


def export(out, timing):
    (out/'timing.json').write_text(json.dumps(timing,indent=2,allow_nan=False)+'\n')
    with (out/'timing.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['arm','trajectories','optimized_designs','recorded_span_seconds','seconds_per_design'])
        writer.writeheader()
        writer.writerows(dict(arm=arm,**{k:v for k,v in data.items() if k!='phase_seconds'}) for arm,data in timing['arms'].items())


def report_section(timing):
    lines=['', '## Recorded time per optimized design', '', DEFINITION, '',
           '| Condition | Seconds / design |', '|---|---:|']
    lines += [f"| {arm} | {value['seconds_per_design']:.1f} |" for arm,value in timing['arms'].items()]
    return lines
