"""Active-job budgets; queue and between-session downtime are never charged.

Checks occur at durable operation boundaries, never halfway through model output.
The broker still owns cancellation, process groups and the exclusive lease.
"""
import json
import os
from pathlib import Path
import threading
import time
from .contract import atomic, fixed, seal, sha, verify


class BudgetExhausted(Exception): pass


def checkpoint():
    deadline=os.environ.get('STUDIO_RFD4_DEADLINE')
    if deadline and time.monotonic() >= float(deadline): raise BudgetExhausted('Design time reached; completed outputs preserved.')


class Clock:
    def __init__(self, output, seconds):
        self.path=Path(output)/'active_time.json'; self.seconds=seconds
        prior=json.loads(self.path.read_text()) if self.path.exists() else {}
        if prior and prior['budget_seconds'] != seconds: raise ValueError('Saved design time changed; use a new plan.')
        self.spent=float(prior.get('active_seconds',0));self.started=time.monotonic();self.stop=threading.Event()
    def save(self):
        atomic(self.path,dict(schema=1,budget_seconds=self.seconds,active_seconds=self.spent+time.monotonic()-self.started))
    def __enter__(self):
        self.previous=os.environ.get('STUDIO_RFD4_DEADLINE')
        os.environ['STUDIO_RFD4_DEADLINE']=str(self.started+max(0,self.seconds-self.spent))
        self.save()
        def heartbeat():
            while not self.stop.wait(1):self.save()
        self.thread=threading.Thread(target=heartbeat,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join();self.save()
        if self.previous is None:os.environ.pop('STUDIO_RFD4_DEADLINE',None)
        else:os.environ['STUDIO_RFD4_DEADLINE']=self.previous


def run(config_path, stage):
    config=json.loads(Path(config_path).read_text());cfg=config['settings'];output=Path(config['output'])
    reason='family_limit';completed=0
    with Clock(output,cfg['time_budget_minutes']*60):
        try:
            for index in range(cfg['count']):
                child=output/'budget_families'/f"seed_{cfg['seed']+index}"
                child.mkdir(parents=True,exist_ok=True)
                child_cfg=dict(config,output=str(child),settings=dict(cfg,count=1,seed=cfg['seed']+index,time_budget_minutes=None))
                if cfg['starting_structures']:child_cfg['settings']['starting_structures']=[cfg['starting_structures'][index]]
                fixed(child/'rfd4_config.json',child_cfg)
                fixed(child/'studio_job.json',json.loads((output/'studio_job.json').read_text()))
                if (child/'completed.json').exists(): verify(child/'completed.json')
                else:
                    checkpoint()
                    stage('run',child/'rfd4_config.json',child)
                completed+=1
                atomic(output/'progress.json',dict(stage='timed-design',completed=completed,time_budget_minutes=cfg['time_budget_minutes']))
        except BudgetExhausted: reason='time_budget'
    rows=[];receipts=[]
    for child in sorted((output/'budget_families').glob('*')):
        selected=list(child.glob('candidates/*/completed.json'))
        if selected:
            rows.extend(verify(p) for p in selected);receipts+=selected
        else:
            for p in child.glob('generation/*/completed.json'):rows.append(verify(p));receipts.append(p)
        for p in child.glob('families/*/final/completed.json'):
            verify(p);rows+=json.loads((p.parent/'results.json').read_text());receipts.append(p)
    atomic(output/'results.json',rows)
    report=dict(reason=reason,complete_families=completed,saved_candidates=len(rows),
        partial_family=any(not (p/'completed.json').exists() and any(p.glob('**/completed.json')) for p in (output/'budget_families').glob('*')),
        time_accounting='active broker execution, including preparation and loading; finish current atomic operation')
    atomic(output/'budget_result.json',report)
    seal(output/'completed.json',report,[Path(config_path),output/'results.json',output/'budget_result.json',output/'active_time.json',*receipts])
    atomic(output/'progress.json',dict(stage='completed',**report))
