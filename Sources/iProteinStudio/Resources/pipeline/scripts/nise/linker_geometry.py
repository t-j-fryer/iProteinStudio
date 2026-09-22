"""Experimental generic carboxamide extension and exterior-access diagnostics.

Ported from the recorded biotin exit-filter trial. Rigid input coordinates; idealised trans amide and alkyl
torsions. Clash allowances/probe radii are trial settings, not calibrated truth.
"""
import numpy as np
from scipy.spatial import cKDTree
from scipy import ndimage
from rdkit import Chem

RAD={z:Chem.GetPeriodicTable().GetRvdw(z) for z in [6,7,8,9,15,16,17,35,53]}
def unit(v):return np.asarray(v)/np.linalg.norm(v)
def sphere(n=96):
 k=np.arange(n)+.5;z=1-2*k/n;t=k*np.pi*(3-np.sqrt(5))
 return np.column_stack((np.sqrt(1-z*z)*np.cos(t),np.sqrt(1-z*z)*np.sin(t),z))

def extensions(c,o,attachment,nphi=24,angles=(115,120,125),cis=False):
 """NCC stub: C-N 1.35, N-C 1.46, C-C 1.52 A; N-C-C 112 degrees."""
 e=unit(attachment-c);n=c+1.35*e
 p=unit((o-c)-np.dot(o-c,e)*e)
 out=[];metadata=[]
 for angle in angles:
  # Trans amide means the acyl-side carbon and N-side carbon are opposite.
  # Carbonyl O is opposite the acyl-side carbon, so O and N-side C are on
  # the SAME side of the C-N axis (O=C-N-C dihedral near zero).
  direction=-np.cos(np.deg2rad(angle))*e+(1 if not cis else -1)*np.sin(np.deg2rad(angle))*p
  c1=n+1.46*direction
  back=unit(n-c1);u=unit(np.cross(back,e));v=np.cross(back,u)
  for phi in np.arange(nphi)*2*np.pi/nphi:
   c2=c1+1.52*(np.cos(np.deg2rad(112))*back+np.sin(np.deg2rad(112))*(np.cos(phi)*u+np.sin(phi)*v))
   out.append([n,c1,c2]);metadata.append([angle,float(phi)])
 return np.array(out),np.array(metadata)

def clashes(stubs,env,ez,core,cz,exclude):
 """Maximum vdW overlap. Permit a larger allowance only for probe N vs N/O."""
 er=np.array([RAD.get(int(z),Chem.GetPeriodicTable().GetRvdw(int(z))) for z in ez])
 cr=np.array([RAD[int(z)] for z in cz])
 d=np.linalg.norm(stubs[:,:,None,:]-env[None,None,:,:],axis=-1)
 ov=np.array([1.55,1.7,1.7])[None,:,None]+er[None,None,:]-d
 # N/O H-bond-compatible close contacts are kept separate from other overlaps.
 polar=(ez==7)|(ez==8)
 pn=ov[:,0,polar].max(axis=1) if polar.any() else np.full(len(stubs),-99.)
 npn=ov[:,0,~polar].max(axis=1) if (~polar).any() else np.full(len(stubs),-99.)
 carbon=ov[:,1:,:].max(axis=(1,2))
 for i in range(3):
  use=np.array([j for j in range(len(core)) if j not in exclude[i]])
  if not len(use):continue
  v=np.array([1.55,1.7,1.7])[i]+cr[use][None,:]-np.linalg.norm(stubs[:,i,None,:]-core[use][None,:,:],axis=-1)
  if i==0:npn=np.maximum(npn,v.max(axis=1))
  else:carbon=np.maximum(carbon,v.max(axis=1))
 return pn,npn,carbon

def ray_clearance(tip,xyz,radii,n=96):
 """Widest sampled infinite straight ray, including the endpoint clearance."""
 dirs=sphere(n);delta=xyz-tip
 proj=np.maximum(delta@dirs.T,0)
 d2=np.maximum(np.sum(delta*delta,axis=1)[:,None]-proj*proj,0)
 gaps=np.sqrt(d2)-radii[:,None]
 clearance=gaps.min(axis=0);best=int(clearance.argmax())
 return float(clearance[best]),dirs[best]

def segment_clear(a,b,xyz,radii,probe):
 v=b-a;norm=np.dot(v,v)
 t=np.clip((xyz-a)@v/norm,0,1) if norm>1e-12 else np.zeros(len(xyz))
 return bool(np.all(np.linalg.norm(xyz-(a+t[:,None]*v),axis=1)>=radii+probe-1e-8))

def exterior(tips,xyz,radii,probe=1.,step=.75):
 """Conservative/optimistic voxel bounds for connectivity to exterior.

Uniform boxes enclose every obstacle plus padding. Cell half-diagonal is used
as a Lipschitz clearance bound. Optimistic 26-neighbour failure implies no
continuous route at this probe size; conservative 6-neighbour pass is a valid
route when its endpoint connector is clear. Intermediate cases are unresolved.
"""
 lo=np.minimum(xyz.min(0),tips.min(0))-5;hi=np.maximum(xyz.max(0),tips.max(0))+5
 shape=np.ceil((hi-lo)/step).astype(int)+1
 if np.prod(shape)>6500000:raise ValueError('Grid exceeds declared memory bound')
 flat=np.arange(np.prod(shape));clear=np.full(len(flat),np.inf,dtype=np.float32)
 trees=[(cKDTree(xyz[radii==r]),r) for r in np.unique(radii)]
 for start in range(0,len(flat),100000):
  end=min(len(flat),start+100000)
  pts=lo+np.column_stack(np.unravel_index(flat[start:end],tuple(shape)))*step
  for tree,r in trees:
   clear[start:end]=np.minimum(clear[start:end],tree.query(pts,workers=1)[0]-r)
 clear=clear.reshape(tuple(shape));margin=np.sqrt(3)*step/2
 def connected(threshold,connectivity):
  mask=clear>=threshold;seed=np.zeros(tuple(shape),dtype=bool)
  for ax in range(3):
   for edge in [0,-1]:
    sl=[slice(None)]*3;sl[ax]=edge;seed[tuple(sl)]=mask[tuple(sl)]
  return ndimage.binary_propagation(seed,structure=ndimage.generate_binary_structure(3,connectivity),mask=mask)
 optimistic=connected(probe-margin,3);conservative=connected(probe+margin,1)
 oi=[];ci=[]
 for tip in tips:
  q=(tip-lo)/step;cell=np.rint(q).astype(int)
  oi.append(bool(optimistic[tuple(cell)]))
  candidates=[]
  for dx in [-1,0,1]:
   for dy in [-1,0,1]:
    for dz in [-1,0,1]:
     j=cell+np.array([dx,dy,dz])
     if np.all(j>=0) and np.all(j<shape) and conservative[tuple(j)]:candidates.append(j)
  ci.append(any(segment_clear(tip,lo+j*step,xyz,radii,probe) for j in candidates))
 return dict(optimistic=oi,conservative=ci,step=step,probe=probe,grid_shape=shape.tolist())

def evaluate(case,nphi=24,nrays=96,grid_step=.75,grid=True):
 core=np.array(case['core']);cz=np.array(case['core_z']);env=np.array(case['environment']);ez=np.array(case['environment_z'])
 c,o,a=np.array(case['attachment_frame'])
 stubs,meta=extensions(c,o,a,nphi=nphi)
 pn,npn,carbon=clashes(stubs,env,ez,core,cz,case['bonded_exclusions'])
 standard=(pn<=.8)&(npn<=.5)&(carbon<=.5)
 lenient=(pn<=1.)&(npn<=.7)&(carbon<=.7)
 strict=(pn<=.6)&(npn<=.3)&(carbon<=.3)
 nominal=meta[:,0]==120
 allxyz=np.vstack((env,core));radii=np.array([RAD.get(int(z),Chem.GetPeriodicTable().GetRvdw(int(z))) for z in np.r_[ez,cz]])
 rays=np.full(len(stubs),-99.);directions={}
 for i in np.flatnonzero(lenient):
  rays[i],direction=ray_clearance(stubs[i,2],allxyz,radii,nrays);directions[int(i)]=direction.tolist()
 best=int(np.argmax(rays)) if lenient.any() else int(np.argmin(np.maximum.reduce([pn-.8,npn-.5,carbon-.5])))
 detail=None
 if not lenient.any():label='blocked';reason='No trans NCC stub fits even with lenient overlap allowances.'
 elif np.count_nonzero(standard&nominal&(rays>=1.4))>=int(np.ceil(nphi/8)):label='open';reason='At least one eighth of nominal trans stubs fit and have a direct 1.4 A continuation route.'
 elif np.any(lenient&(rays>=1.)):label='restricted';reason='At least one permissive continuation route; broad-access criterion not met.'
 elif grid:
  selected=np.flatnonzero(lenient)
  detail=exterior(stubs[selected,2],allxyz,radii,probe=1.,step=grid_step)
  if any(detail['conservative']):label='restricted';reason='A curved continuation route is certified by the conservative grid.'
  elif not any(detail['optimistic']):label='blocked';reason='Even the optimistic grid has no exterior connection for a 1 A continuation probe.'
  else:label='unresolved';reason='Grid bounds disagree; do not reject on this calculation.'
 else:label='unresolved';reason='No sampled straight exit; curved test not performed.'
 cis_stubs,_=extensions(c,o,a,nphi=nphi,cis=True)
 cp,cn,cc=clashes(cis_stubs,env,ez,core,cz,case['bonded_exclusions'])
 cisfits=(cp<=1.)&(cn<=.7)&(cc<=.7)
 cis_possible=False
 if label=='blocked' and cisfits.any():
  cis_tips=cis_stubs[cisfits,2]
  cis_possible=any(ray_clearance(t,allxyz,radii,nrays)[0]>=1. for t in cis_tips)
  if not cis_possible and grid:
   cis_possible=any(exterior(cis_tips,allxyz,radii,probe=1.,step=grid_step)['optimistic'])
  if cis_possible:label='unresolved';reason+=' A cis stub may exit; alternative amide geometry requires review.'
 return dict(id=case['id'],label=label,reason=reason,n_stubs=len(stubs),strict_fit=int(strict.sum()),standard_fit=int(standard.sum()),
 lenient_fit=int(lenient.sum()),cis_lenient_fit=int(cisfits.sum()),cis_exit_possible=cis_possible,nominal_standard_fit=int((standard&nominal).sum()),
 nominal_wide_exit=int((standard&nominal&(rays>=1.4)).sum()),best_ray_radius_a=float(rays.max()) if lenient.any() else None,
 ray_counts={str(r):int((lenient&(rays>=r)).sum()) for r in [.8,1.,1.2,1.4,1.6]},
 best_stub=stubs[best].tolist(),best_stub_overlaps_a=dict(polar_n=float(pn[best]),other_n=float(npn[best]),carbon=float(carbon[best])),
 best_ray_direction=directions.get(best),grid=detail,
 protocol={'nphi':nphi,'nrays':nrays,'grid_step':grid_step,'geometry':'trans amide; C-N-C 115/120/125; N-C-C 112; no relaxation'})


def guarded(case,nphi=24):
 core=np.array(case['core']);cz=np.array(case['core_z']);env=np.array(case['environment']);ez=np.array(case['environment_z'])
 stubs,meta=extensions(*np.array(case['attachment_frame']),nphi=nphi,angles=(120,))
 pn,npn,carbon=clashes(stubs,env,ez,core,cz,case['bonded_exclusions']);fit=(pn<=.8)&(npn<=.5)&(carbon<=.5)
 xyz=np.vstack((env,core));radii=np.array([Chem.GetPeriodicTable().GetRvdw(int(z)) for z in np.r_[ez,cz]])
 best=[]
 for s,ok in zip(stubs,fit):
  if not ok:best.append(-99.);continue
  tip=s[2];forward=unit(s[2]-s[1]);u=unit(np.cross(forward,s[0]-s[1]));v=np.cross(forward,u)
  dirs=[]
  for angle in [50,68,85]:
   theta=np.deg2rad(angle)
   for phi in np.arange(24)*2*np.pi/24:
    dirs.append(np.cos(theta)*forward+np.sin(theta)*(np.cos(phi)*u+np.sin(phi)*v))
  dirs=np.array(dirs);delta=xyz-tip;proj=np.maximum(delta@dirs.T,0)
  d2=np.maximum(np.sum(delta*delta,axis=1)[:,None]-proj*proj,0);gap=(np.sqrt(d2)-radii[:,None]).min(axis=0)
  # At the next atom centre, N is beyond the bonded 1-3 neighbourhood.
  # C1 is a 1-3 neighbour there, so include it after a second 1.52 A step.
  for atom,r,start in [(s[0],1.55,1.52),(s[1],1.7,3.04)]:
   origin=tip+start*dirs;d=atom-origin;t=np.maximum(np.sum(d*dirs,axis=1),0)
   gap=np.minimum(gap,np.sqrt(np.maximum(np.sum(d*d,axis=1)-t*t,0))-r)
  best.append(float(gap.max()))
 return dict(id=case['id'],nphi=nphi,wide_forward_count=sum(x>=1.4 for x in best),required_count=int(np.ceil(nphi/8)),
             maximum_forward_radius_a=max(best),broad_forward_exit=sum(x>=1.4 for x in best)>=int(np.ceil(nphi/8)))
