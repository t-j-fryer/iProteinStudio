"""Track owned descendants across process-group changes without reading argv/env.

Keep observed identities after reparenting. Never signal an unrelated process
just because it has opened Studio's lock file. This is supervision of ordinary
workflow children, not containment of deliberately evasive daemon processes.
"""
import os
import signal
import subprocess
import time


def snapshot():
    result = subprocess.run(
        ['/bin/ps', '-axo', 'pid=,ppid=,pgid=,stat=,lstart='],
        check=True, capture_output=True, text=True, timeout=3)
    records = {}
    for line in result.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) != 5:
            continue
        pid, parent, group = map(int, fields[:3])
        records[pid] = dict(parent=parent, group=group, state=fields[3], born=fields[4])
    return records


class ProcessTree:
    def __init__(self, leader):
        self.leader = leader
        self.known = {}
        self.last_scan = 0.
        self.refresh(force=True)

    def refresh(self, force=False):
        if not force and time.monotonic() - self.last_scan < .5:
            return
        rows = snapshot()
        owned = {pid for pid, born in self.known.items()
                 if pid in rows and rows[pid]['born'] == born}
        # Only initially adopt the leader's group. Once observed, identity must
        # continue matching even if a PID or group number is later reused.
        if not self.known and self.leader in rows:
            owned.add(self.leader)
        group_live = (self.leader in owned or
                      (self.leader in self.known and self.leader not in rows) or
                      any(rows[pid]["group"] == self.leader for pid in owned))
        changed = True
        while changed:
            previous = len(owned)
            owned.update(pid for pid, row in rows.items()
                         if row['parent'] in owned or (group_live and row['group'] == self.leader))
            changed = len(owned) != previous
        self.known.update({pid: rows[pid]['born'] for pid in owned})
        self.last_scan = time.monotonic()

    def alive(self):
        rows = snapshot()
        return {pid: row for pid, row in rows.items()
                if self.known.get(pid) == row['born'] and not row['state'].startswith('Z')}

    def send(self, signum):
        self.refresh(force=True)
        # Snapshot immediately before signalling, rejecting PID reuse. Children
        # receive the signal even after setsid() moves them out of the group.
        live = self.alive()
        for pid in sorted(live, key=lambda pid: pid == self.leader):
            try:
                os.kill(pid, signum)
            except ProcessLookupError:
                pass
