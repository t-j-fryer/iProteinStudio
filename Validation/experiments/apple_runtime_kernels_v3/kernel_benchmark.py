"""Independent NumPy FP64 oracle and alternating synchronized wrapper timing."""
import time
import numpy as np
from metal_ops import MetalOps

def run(torch):
    start=time.monotonic();ops=MetalOps(torch);compile_seconds=time.monotonic()-start
    rng=np.random.default_rng(1917);rows=[]
    for shape in [(1,76,128),(3,96,384),(1,768,256),(96,96,512),(256,256,512)]:
        a,b,c=[rng.normal(size=shape).astype('float32') for _ in range(3)]
        # Include tails and exact zeros without overflowing the float64 oracle.
        a.reshape(-1)[:5]=[-80,-20,0,20,80]
        x,y,z=[torch.from_numpy(v).to('mps') for v in (a,b,c)]
        for name,values,ref,stock in [
            ('silu_mul',(x,y),(a.astype('float64')/(1+np.exp(-a.astype('float64'))))*b,
             lambda:torch.nn.functional.silu(x)*y),
            ('gate_mul',(x,y),b/(1+np.exp(-a.astype('float64'))),lambda:torch.sigmoid(x)*y),
            ('gate_add',(x,y,z),b/(1+np.exp(-a.astype('float64')))+c,lambda:torch.sigmoid(x)*y+z)]:
            candidate=lambda:ops.call(name,*values)
            got=candidate().cpu().numpy();old=stock().cpu().numpy()
            error=float(np.linalg.norm((got-ref).ravel())/np.linalg.norm(ref.ravel()))
            stock_error=float(np.linalg.norm((got-old).ravel())/max(np.linalg.norm(old.ravel()),1e-12))
            passed=bool(np.isfinite(got).all() and error<=1e-5 and stock_error<=1e-5)
            for _ in range(8):stock();candidate()
            times={'stock':[],'metal':[]}
            for repeat in range(4):
                order=[('stock',stock),('metal',candidate)]
                if repeat%2:order.reverse()
                for label,fn in order:
                    torch.mps.synchronize();t=time.monotonic()
                    for _ in range(20):fn()
                    torch.mps.synchronize();times[label].append((time.monotonic()-t)/20)
            rows.append(dict(name=name,shape=shape,oracle_relative_l2=error,stock_relative_l2=stock_error,
                             passed=passed,seconds=times))
    return dict(torch=torch.__version__,compile_seconds=compile_seconds,rows=rows,passed=all(r['passed'] for r in rows))
