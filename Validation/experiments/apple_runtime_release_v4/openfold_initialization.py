"""Skip only Linear truncated-normal initializers overwritten by a strict load.

Experimental per-process patch. Every skipped tensor must be a checkpointed
parameter, and is compared byte-for-byte with its loaded checkpoint value.
"""
import weakref
class CheckpointCoverage:
 def __init__(self,torch):
  self.torch=torch;self.pending=[];self.evidence=dict(skipped_initializers=0,verified_parameters=0,verified_elements=0,strict_loads=0,discarded_modules=0,verified_initializers=0)
 def skip(self,weight,owner):
  if owner.weight is not weight:raise RuntimeError('Initializer does not own the declared Linear weight')
  with self.torch.no_grad():weight.zero_()
  # Keep each event: Python may reuse an id after a temporary layer is freed.
  self.pending.append(weakref.ref(owner));self.evidence['skipped_initializers']+=1
 def verify_load(self,module,state,strict,load,*args,**kwargs):
  live={id(ref()):ref() for ref in self.pending if ref() is not None}
  owners={id(m):(name,m) for name,m in module.named_modules() if id(m) in live}
  selected={name+'.weight' if name else 'weight':m.weight for name,m in owners.values()}
  if not strict:raise RuntimeError('Skipped initialization requires a strict checkpoint load')
  if set(owners)!=set(live):raise RuntimeError('A live skipped Linear is not covered by this checkpoint module')
  if not selected or any(name not in state for name in selected):raise RuntimeError('Checkpoint is missing a skipped initialized parameter')
  result=load(module,state,strict,*args,**kwargs)
  # Parameter objects can be replaced during construction; verify the complete
  # final parameter tree, not stale initializer tensor identities.
  for name,p in module.named_parameters():
   if name not in state or p.dtype!=state[name].dtype or not self.torch.equal(p,state[name]):raise RuntimeError('Final parameter differs from checkpoint: '+name)
  for name,p in selected.items():
   if p.dtype!=state[name].dtype or not self.torch.equal(p,state[name]):raise RuntimeError('Checkpoint parameter was not copied exactly: '+name)
   self.evidence['verified_parameters']+=1;self.evidence['verified_elements']+=p.numel()
  self.evidence['discarded_modules']+=sum(ref() is None for ref in self.pending)
  self.evidence['verified_initializers']+=sum(ref() is not None for ref in self.pending)
  self.pending.clear();self.evidence['strict_loads']+=1
  return result
 def guard(self):
  if self.pending or not self.evidence['strict_loads']:raise RuntimeError('Inference forbidden before full checkpoint coverage')

def install(torch):
 from openfold3.core.model.primitives import linear
 from openfold3.projects.of3_all_atom.model import OpenFold3
 coverage=CheckpointCoverage(torch)
 active=[];construct=linear.Linear.__init__
 def constructor(owner,*args,**kwargs):
  active.append(owner)
  try:return construct(owner,*args,**kwargs)
  finally:active.pop()
 def skip(weight):
  if not active:raise RuntimeError('Initialization skipped outside an owned Linear constructor')
  coverage.skip(weight,active[-1])
 linear.Linear.__init__=constructor
 linear.lecun_normal_init_=skip;linear.he_normal_init_=skip
 load=torch.nn.Module.load_state_dict
 def checked(module,state_dict,strict=True,*args,**kwargs):
  if coverage.pending:return coverage.verify_load(module,state_dict,strict,load,*args,**kwargs)
  return load(module,state_dict,strict,*args,**kwargs)
 torch.nn.Module.load_state_dict=checked
 forward=OpenFold3.forward
 def guarded(*args,**kwargs):
  coverage.guard();return forward(*args,**kwargs)
 OpenFold3.forward=guarded
 return coverage.evidence
