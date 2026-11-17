// Usage: node tools/molart/build.mjs PINNED_SOURCE_DIR OUTPUT_DIR
// npm ci --ignore-scripts in PINNED_SOURCE_DIR first, using its upstream lockfile.
import { resolve,join } from 'node:path';
import { readFile,writeFile,cp,mkdir,rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const source=resolve(process.argv[2]),output=resolve(process.argv[3]);
const upstream=JSON.parse(await readFile('tools/molart/upstream-manifest.json','utf8'));
for(const [name,expected] of Object.entries(upstream.files)) {
  const actual=createHash('sha256').update(await readFile(join(source,name))).digest('hex');
  if(actual!==expected)throw Error('Pinned upstream source differs: '+name);
}
const {build}=await import(pathToFileURL(join(source,'node_modules/vite/dist/node/index.js')).href);
const scratch=join(source,'.studio-build');await rm(scratch,{recursive:true,force:true});await mkdir(scratch,{recursive:true});
await cp('tools/molart/entry.ts',join(scratch,'entry.ts'));await cp(join(source,'src'),join(scratch,'upstream/src'),{recursive:true});
// Native renderer switching must disconnect the upstream canvas observer.
const rendererPath=join(scratch,'upstream/src/renderer/renderer.ts');
let rendererSource=await readFile(rendererPath,'utf8');
if(!rendererSource.includes('new ResizeObserver(() => { this.controls.handleResize(); this.invalidate(); }).observe(canvas);')) throw Error('Pinned observer patch no longer applies');
rendererSource=rendererSource.replace('  private raf = 0;', '  private raf = 0;\n  private resizeObserver: ResizeObserver | null = null;');
rendererSource=rendererSource.replace('new ResizeObserver(() => { this.controls.handleResize(); this.invalidate(); }).observe(canvas);','(this.resizeObserver = new ResizeObserver(() => { this.controls.handleResize(); this.invalidate(); })).observe(canvas);');
rendererSource=rendererSource.replace('  dispose() {','  dispose() {\n    this.resizeObserver?.disconnect();');
await writeFile(rendererPath,rendererSource);
await build({configFile:false,root:source,publicDir:false,build:{target:'es2022',outDir:output,emptyOutDir:false,minify:true,lib:{entry:join(scratch,'entry.ts'),name:'StudioMolart',formats:['iife'],fileName:()=> 'molart.js'},rollupOptions:{output:{inlineDynamicImports:true}}}});
await cp(join(source,'LICENSE'),join(output,'LICENSE-Molart.txt'));await cp(join(source,'node_modules/three/LICENSE'),join(output,'LICENSE-Three.txt'));
const hash=async p=>createHash('sha256').update(await readFile(p)).digest('hex');
const manifest={schema:1,repository:upstream.repository,commit:upstream.commit,license:'MIT',three:JSON.parse(await readFile(join(source,'node_modules/three/package.json'),'utf8')).version,upstream_lock_sha256:await hash(join(source,'package-lock.json')),adapter_sha256:await hash('tools/molart/entry.ts'),build_script_sha256:await hash('tools/molart/build.mjs'),bundle_sha256:await hash(join(output,'molart.js')),lifecycle_patch:'Retain and disconnect upstream ResizeObserver; release cached WebGL resources on renderer switch; apply native input when RAF is throttled',runtime_network:false};
await writeFile(join(output,'UPSTREAM.json'),JSON.stringify(manifest,null,2)+'\n');await rm(scratch,{recursive:true,force:true});
