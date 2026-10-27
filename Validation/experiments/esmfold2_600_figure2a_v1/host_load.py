"""Low-frequency process-load observations; no process is stopped or changed."""
import os
import subprocess
import time
from pathlib import Path

COMPILERS = {'swift', 'swiftc', 'swift-frontend', 'swift-build', 'clang', 'clang++',
             'cc1', 'ld', 'ld64', 'xcodebuild', 'ninja', 'make'}


def classify(rows, root_pid):
    owned = {root_pid}
    while True:
        expanded = owned | {r['pid'] for r in rows if r['ppid'] in owned}
        if expanded == owned:
            break
        owned = expanded
    external = [r for r in rows if r['pid'] not in owned]
    return dict(external_cpu_percent=sum(r['cpu'] for r in external),
                compilers=[r for r in external if r['executable'] in COMPILERS],
                external_hot_processes=[r for r in external if r['cpu'] >= 25],
                owned_pids=sorted(owned))


def snapshot():
    text = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,pcpu=,rss=,comm='], text=True)
    rows = []
    for line in text.splitlines():
        p = line.split(None, 4)
        if len(p) == 5:
            rows.append(dict(pid=int(p[0]), ppid=int(p[1]), cpu=float(p[2]),
                             rss_bytes=int(p[3])*1024, executable=Path(p[4]).name))
    if len(rows) < 10:
        raise RuntimeError('Process visibility insufficient to qualify timing')
    return dict(unix=time.time(), **classify(rows, os.getpid()))


def acceptable(row):
    return not row['compilers'] and row['external_cpu_percent'] < 200


def audit(rows):
    longest = current = 0
    for row in rows:
        current = current + 1 if row['external_cpu_percent'] >= 200 else 0
        longest = max(longest, current)
    compilers = [r for r in rows if r['compilers']]
    return dict(samples=len(rows), compiler_samples=len(compilers),
                longest_high_external_cpu_samples=longest,
                max_external_cpu_percent=max((r['external_cpu_percent'] for r in rows), default=0),
                timing_qualified=bool(rows) and not compilers and longest < 3,
                qualification='No sampled external compiler; external CPU below200% except transient spikes (<3 consecutive5s samples). Ordinary desktop activity remains; not proof of zero contention.')
