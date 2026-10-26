"""Sample managed workflow memory; no allocation limits or GPU synchronization.

Darwin rusage_info_v2 layout and counters follow the existing prediction_scale_v1
collector. Accounted footprint and RSS are separate ledgers, not additive RAM.
"""
import ctypes
import json
import platform
import time
import uuid
from pathlib import Path
from .common import atomic_json, utc_now


class Usage(ctypes.Structure):
    _fields_ = [('uuid', ctypes.c_uint8 * 16)] + [(x, ctypes.c_uint64) for x in
        'user system idle interrupts pageins wired rss footprint start exit child_user child_system child_idle child_interrupts child_pageins child_elapsed read written'.split()]


class Swap(ctypes.Structure):
    _fields_ = [('total', ctypes.c_uint64), ('avail', ctypes.c_uint64), ('used', ctypes.c_uint64),
                ('pagesize', ctypes.c_uint32), ('encrypted', ctypes.c_int)]


def process_memory(pid):
    lib = ctypes.CDLL('/usr/lib/libproc.dylib')
    lib.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    data = Usage()
    if lib.proc_pid_rusage(pid, 2, ctypes.byref(data)):
        return None
    return dict(pid=pid, rss_bytes=data.rss, footprint_bytes=data.footprint)


def system_memory():
    lib = ctypes.CDLL(None)
    swap = Swap(); size = ctypes.c_size_t(ctypes.sizeof(swap))
    used = None if lib.sysctlbyname(b'vm.swapusage', ctypes.byref(swap), ctypes.byref(size), None, 0) else swap.used
    pressure = ctypes.c_int(); size = ctypes.c_size_t(ctypes.sizeof(pressure))
    level = None if lib.sysctlbyname(b'kern.memorystatus_vm_pressure_level', ctypes.byref(pressure), ctypes.byref(size), None, 0) else pressure.value
    total = ctypes.c_uint64(); size = ctypes.c_size_t(ctypes.sizeof(total))
    ram = None if lib.sysctlbyname(b'hw.memsize', ctypes.byref(total), ctypes.byref(size), None, 0) else total.value
    return dict(system_swap_used_bytes=used, system_pressure=level, installed_memory_bytes=ram)


class Sampler:
    def __init__(self, directory, policy, command):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / ('memory-' + uuid.uuid4().hex + '.jsonl')
        self.summary_path = self.path.with_suffix('.summary.json')
        self.last = -float('inf')
        self.summary = dict(schema=1, started_at=utc_now(), policy=policy, command=command,
            platform=platform.platform(), machine=platform.machine(), samples=0, complete_samples=0,
            errors=0, peaks={}, raw_path=str(self.path), nominal_interval_seconds=1,
            interpretation='Sampled workflow process-tree accounted footprint and RSS, separately. Shared pages may be counted more than once. Neither is exact physical RAM. System swap/pressure include other apps. No automatic profile promotion.')
        self.path.touch(exist_ok=False)
        atomic_json(self.summary_path, self.summary)

    def sample(self, family, stage):
        now = time.monotonic()
        if now - self.last < 1:
            return
        self.last = now
        row = dict(recorded_at=utc_now(), monotonic_seconds=now, stage=stage)
        try:
            live = family.alive()  # Reject stale process identities, including reused PIDs.
            values = [process_memory(pid) for pid in live]
            missing = [pid for pid, value in zip(live, values) if value is None]
            values = [v for v in values if v is not None]
            row.update(processes=values, unavailable_pids=missing, complete=bool(live) and not missing,
                       **system_memory())
            # Missing readings are unknown, not a deceptively small tree total.
            row['tree_rss_bytes'] = sum(v['rss_bytes'] for v in values) if row['complete'] else None
            row['tree_footprint_bytes'] = sum(v['footprint_bytes'] for v in values) if row['complete'] else None
            self.summary['complete_samples'] += int(row['complete'])
            for key in ('tree_rss_bytes', 'tree_footprint_bytes', 'system_swap_used_bytes'):
                if row[key] is not None:
                    self.summary['peaks'][key] = max(row[key], self.summary['peaks'].get(key, 0))
        except Exception as exc:
            row.update(sampling_error=str(exc), complete=False)
            self.summary['errors'] += 1
        self.summary['samples'] += 1
        with self.path.open('a') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
        atomic_json(self.summary_path, self.summary)

    def finish(self, code):
        self.summary.update(finished_at=utc_now(), exit_code=code)
        atomic_json(self.summary_path, self.summary)
