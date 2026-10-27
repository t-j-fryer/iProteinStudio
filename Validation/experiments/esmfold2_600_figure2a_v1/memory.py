"""Darwin process-tree physical footprint/RSS, sampled without GPU fences."""
import ctypes, json, os, threading, time
from pathlib import Path

class Usage(ctypes.Structure):
    _fields_=[('uuid',ctypes.c_uint8*16)]+[(x,ctypes.c_uint64) for x in
       'user system idle interrupts pageins wired rss footprint start exit child_user child_system child_idle child_interrupts child_pageins child_elapsed read written'.split()]

LIB=ctypes.CDLL('/usr/lib/libproc.dylib')
LIB.proc_pid_rusage.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
LIB.proc_listchildpids.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_int]

def process_memory(pid):
    data=Usage()
    if LIB.proc_pid_rusage(pid,2,ctypes.byref(data)):return None
    return dict(pid=pid,rss_bytes=data.rss,footprint_bytes=data.footprint)

def tree_memory(pid):
    queue=[pid];seen=set();values=[]
    while queue:
        current=queue.pop()
        if current in seen:continue
        seen.add(current);record=process_memory(current)
        if record:values.append(record)
        children=(ctypes.c_int*4096)();n=LIB.proc_listchildpids(current,children,ctypes.sizeof(children))
        if n>0:queue.extend(x for x in children[:min(n,4096)] if x>0)
    return dict(processes=values,tree_rss_bytes=sum(v['rss_bytes'] for v in values),
                tree_footprint_bytes=sum(v['footprint_bytes'] for v in values))

class Swap(ctypes.Structure):
    _fields_=[('total',ctypes.c_uint64),('avail',ctypes.c_uint64),('used',ctypes.c_uint64),('pagesize',ctypes.c_uint32),('encrypted',ctypes.c_int)]

def swap_bytes():
    data=Swap();size=ctypes.c_size_t(ctypes.sizeof(data));lib=ctypes.CDLL(None)
    if lib.sysctlbyname(b'vm.swapusage',ctypes.byref(data),ctypes.byref(size),None,0):return None
    return data.used

class Sampler:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.scope='initialization';self.stage=lambda:'initialization';self.gpu=lambda:{}
        self.stop=threading.Event();self.thread=threading.Thread(target=self.loop,daemon=True)
        self.thread.start()
    def loop(self):
        with self.path.open('x',buffering=1) as f:
            while not self.stop.is_set():
                try:
                    r=dict(unix=time.time(),scope=self.scope,stage=self.stage(),swap_used_bytes=swap_bytes(),**tree_memory(os.getpid()),**self.gpu())
                except Exception as e:r=dict(unix=time.time(),scope=self.scope,sampling_error=repr(e))
                f.write(json.dumps(r)+'\n');self.stop.wait(0.5)
    def close(self):self.stop.set();self.thread.join(3)

def summarize(path,scope=None):
    rows=[json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    if scope is not None:rows=[r for r in rows if r['scope']==scope]
    keys=('tree_rss_bytes','tree_footprint_bytes','mps_active_bytes','mps_driver_bytes','mlx_active_bytes','mlx_cache_bytes','mlx_peak_bytes','swap_used_bytes')
    return dict(samples=len(rows),peaks={k:max(r[k] for r in rows if r.get(k) is not None) for k in keys if any(r.get(k) is not None for r in rows)},
                first_swap_bytes=next((r['swap_used_bytes'] for r in rows if r.get('swap_used_bytes') is not None),None))
