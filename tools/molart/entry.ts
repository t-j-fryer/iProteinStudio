// Studio adapter. Upstream parsing, geometry, styles and shaders are unchanged.
import { MolartRenderer } from './upstream/src/renderer/renderer';
import { loadStructure } from './upstream/src/io/load';
import { coordinateFingerprint } from './upstream/src/model/structure';
import { allStyles, getStyle } from './upstream/src/art/registry';

export const styles = allStyles().map(s => ({id:s.id,label:s.label,technique:s.technique,artNote:s.art?.note || ''}));
export function create(canvas: HTMLCanvasElement) {
  const renderer = new MolartRenderer(canvas);
  renderer.style = getStyle('normal');
  renderer.params = {seed:7,deform:0,art:false,faces:false};
  // WKWebView can throttle RAF in inactive native windows. Apply native input
  // after upstream TrackballControls have consumed the event, then draw once.
  let retired=false, refinement=0;
  const interact = (event: Event) => {
    if(event.type==='pointermove' && !(event as PointerEvent).buttons) return;
    queueMicrotask(() => {
    if(retired) return;
    renderer.controls.update(); renderer.invalidate(); renderer.renderToCanvas('fast');
    clearTimeout(refinement);
    refinement=window.setTimeout(()=>{if(!retired)renderer.renderToCanvas('full');},200);
    });
  };
  canvas.addEventListener('wheel',interact,{passive:true});
  canvas.addEventListener('pointermove',interact,{passive:true});
  let original: ReturnType<typeof loadStructure> | null = null;
  let fingerprint: string | null = null;
  const observer = new ResizeObserver(() => renderer.invalidate()); observer.observe(canvas);
  return {
    load(text: string, name: string, align?: (coords:number[][], sites:Record<string,number[]>) => number[][]) {
      const parsed = loadStructure(text,name); original = parsed; fingerprint = coordinateFingerprint(parsed);
      let display = parsed;
      if (align) {
        const sites: Record<string,number[]> = {};
        for (const residue of parsed.residues) {
          if (!residue.chainId || residue.chainId === 'A') continue;
          const at = residue.ca * 3;
          sites[residue.chainId + ':' + residue.resSeq] = Array.from(parsed.coords.slice(at,at+3));
        }
        const points:number[][]=[];
        for(let i=0;i<parsed.coords.length;i+=3) points.push(Array.from(parsed.coords.slice(i,i+3)));
        display = Object.freeze({...parsed,coords:new Float64Array(align(points,sites).flat())});
      }
      renderer.setStructure(display);
      return {residues:parsed.residues.length,chains:parsed.chains.map(c=>c.id),notes:parsed.notes,ssSource:parsed.ssSource};
    },
    style(id:string) { renderer.setStyle(getStyle(id)); },
    params(value:object) { renderer.setParams(value); },
    chainStyles(value:Record<string,string>) { renderer.setChainStyles(Object.fromEntries(Object.entries(value).map(([k,v])=>[k,getStyle(v)]))); },
    chainArt(value:Record<string,boolean>) { renderer.setChainArt(value); },
    fit(chains:string[]=[]) { renderer.frameChains(chains); },
    camera() { return renderer.getCameraState(); },
    restoreCamera(value: ReturnType<MolartRenderer['getCameraState']>) { renderer.setCameraState(value); },
    png(size:number) { return renderer.exportPNG(size,size); },
    pixels(size=128) { return Array.from(renderer.renderPixels(size,size)); },
    state() { return {fingerprint,unchanged:original ? coordinateFingerprint(original)===fingerprint : true,
      cacheBytes:renderer.geometryCacheBytes(),chains:renderer.getChainStyles(),camera:renderer.getCameraState()}; },
    dispose() {
      retired=true;clearTimeout(refinement);
      canvas.removeEventListener('wheel',interact);canvas.removeEventListener('pointermove',interact);
      observer.disconnect(); renderer.dispose();
      // Upstream's dispose stops RAF/controls; additionally release its cached
      // WebGL resources when switching renderers in a long-lived native window.
      const r = renderer as any;
      for(const map of [r.geomCache,r.matCache,r.peelCache]) {for(const resource of map.values()) resource.dispose();map.clear();}
      for(const set of r.targetSets.values()) for(const resource of Object.values(set) as any[]) resource?.dispose();
      r.targetSets.clear();
      for(const layer of r.layers) layer.depth.dispose();
      for(const geometry of r.blended) geometry.dispose();
      for(const resource of [r.sunTarget,r.fastOut,r.chainTex,r.dummyTex,r.compositeMat,r.downMat,r.asciiMat,r.quad.geometry]) resource?.dispose();
      r.asciiMat.uniforms.tGlyph.value?.dispose();
      r.renderer.forceContextLoss();
      original=null;fingerprint=null;
    }
  };
}
