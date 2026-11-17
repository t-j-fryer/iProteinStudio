/* Optional offline Molart renderer. Scientific coordinates/verdicts are untouched. */
(function () {
  'use strict';
  const el=id=>document.getElementById(id), root=el('studioViewerRoot'), menu=el('imageStyle');
  const host=el('molartCanvas'), panel=el('molartPanel'), bridge=window.studioSurfaceBridge;
  let library, engine=null, payloads=[], active=false, ready=false, error='', generation=0;
  let frameIndex=-1, chainStyles={}, chainArt={}, lastInfo=null, priorControls=[], priorRotate=false;
  let selectedStyle='normal', selectedArt=false, selectable=false, disposed=0, created=0;
  const frames=()=>bridge.renderer.objectsData[bridge.renderer.currentObjectName]?.frames || [];
  const note=text=>{el('molartNote').textContent=text;el('molartNote').hidden=!text;};
  const decode=encoded=>new TextDecoder().decode(Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)));
  function ensureLibrary() {
    if(window.StudioMolart)return Promise.resolve();
    if(!library) library=new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src='../molart/molart.js';
      script.onload=resolve;script.onerror=()=>{library=null;script.remove();reject(Error('Bundled Molart could not load. Choose Illustration or Paper pocket.'));};
      document.head.appendChild(script);
    });
    return library;
  }
  function clear() {
    ready=false;frameIndex=-1;lastInfo=null;
    if(engine){engine.dispose();engine=null;disposed++;}
    host.replaceChildren();
  }
  function fail(reason) {
    error=String(reason?.message || reason);clear();note(error);el('saveImageButton').disabled=active;
  }
  function settings() {
    const text=el('molartSeed').value.trim(),seed=Number(text);
    if(!/^\d+$/.test(text)||!Number.isInteger(seed)||seed<0||seed>2147483647)throw Error('Use an illustration seed from 0 to 2147483647.');
    return {seed,deform:selectedArt?Number(el('molartDeform').value):0,art:selectedArt,faces:el('molartFaces').checked,
      light:el('molartSun').checked?{angle:Number(el('molartLight').value),color:[1,.94,.84]}:null};
  }
  function updateNote() {
    if(!lastInfo)return;
    const art=selectedArt || Object.values(chainArt).some(Boolean);
    el('molartArtWarning').hidden=!art;
    el('molartArtWarning').textContent=art?'Art mode reshapes the drawing.':'';
    note('');
  }
  function applySettings() {
    if(!engine||!ready)return;
    try{
      engine.params(settings());engine.style(selectedStyle);engine.chainStyles(chainStyles);engine.chainArt(chainArt);
      error='';updateNote();el('saveImageButton').disabled=false;
    }catch(e){error=String(e?.message||e);note(error);el('saveImageButton').disabled=true;}
  }
  function fillChains() {
    const chooser=el('molartChain'), previous=chooser.value;
    chooser.replaceChildren(new Option('Every chain',''));
    for(const chain of lastInfo.chains)chooser.add(new Option('Chain '+(chain||'(blank)'),chain));
    chooser.value=lastInfo.chains.includes(previous)?previous:'';
    syncChainUI();
  }
  function syncChainUI() {
    const chain=el('molartChain').value;
    el('molartChainStyle').value=chain?(chainStyles[chain]||selectedStyle):selectedStyle;
    el('molartArt').checked=chain?(chainArt[chain]??selectedArt):selectedArt;
    el('molartDeform').disabled=!el('molartArt').checked;
  }
  function showFrame(index) {
    if(!active||!engine||!payloads.length)return;
    for(const id of ['playButton','speedButton','overlayButton'])el(id).disabled=true;
    if(index===frameIndex&&ready)return;
    const payload=payloads[index];if(!payload){fail(Error('The selected trajectory frame is unavailable.'));return;}
    const camera=payloads.length>1&&frameIndex>=0?engine.camera():null;
    ready=false;
    try{
      // Keep the same target alignment as the validated py2Dmol trajectory.
      let align;
      if(payloads.length>1&&index>0){
        const reference=new Map();frames()[index].coords.forEach((p,i)=>{
          const frame=frames()[index];if(frame.position_types[i]==='P'&&frame.chains[i]&&frame.chains[i]!=='A')reference.set(frame.chains[i]+':'+frame.residue_numbers[i],p);
        });
        align=(coords,sites)=>{const keys=[...reference.keys()].filter(k=>sites[k]);if(keys.length<3)throw Error('Molart trajectory needs three common target Cα atoms on chains B onward.');return bridge.rigidlyAlignCoordinates(coords,keys.map(k=>sites[k]),keys.map(k=>reference.get(k)));};
      }
      lastInfo=engine.load(decode(payload.encoded),payload.name||('structure.'+(payload.format==='pdb'?'pdb':'cif')),align);
      if(camera)engine.restoreCamera(camera);
      frameIndex=index;ready=true;fillChains();applySettings();
    }catch(e){fail(e);}
  }
  async function enter() {
    const token=++generation;clear();error='';note('Loading local Molart renderer…');el('saveImageButton').disabled=true;
    try{
      await ensureLibrary();if(!active||token!==generation)return;
      if(!payloads.length)throw Error('Load a protein structure before choosing Molart.');
      const canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Molart protein illustration. Drag to rotate, scroll to zoom, right-drag to pan.');canvas.tabIndex=0;host.replaceChildren(canvas);
      engine=window.StudioMolart.create(canvas);created++;showFrame(Math.max(0,bridge.renderer.currentFrame));
    }catch(e){if(token===generation)fail(e);}
  }
  function toggle(value) {
    const entering=value==='molart';
    if(entering===active){if(active){applySettings();syncChainUI();}return;}
    active=entering;root.classList.toggle('studio-molart',active);panel.hidden=!active;
    if(active){
      priorRotate=bridge.renderer.autoRotate;bridge.renderer.autoRotate=false;
      if(bridge.renderer.rotationCheckbox)bridge.renderer.rotationCheckbox.checked=false;
      if(bridge.renderer.isPlaying)bridge.renderer.togglePlay();
      priorControls=['playButton','speedButton','overlayButton'].map(id=>[el(id),el(id).disabled,el(id).title]);
      for(const [control]of priorControls){control.disabled=true;control.title='Use Illustration for playback/overlay. Molart supports cycle scrubbing.';}
      el('saveImageButton').textContent='Save PNG';void enter();
    }else{
      ++generation;clear();for(const [control,disabled,title]of priorControls){control.disabled=disabled;control.title=title;}priorControls=[];
      bridge.renderer.updateUIControls();bridge.renderer.autoRotate=priorRotate&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if(bridge.renderer.rotationCheckbox)bridge.renderer.rotationCheckbox.checked=bridge.renderer.autoRotate;
      el('saveImageButton').textContent='Save';el('saveImageButton').disabled=false;bridge.renderer.render('return from Molart');
    }
  }
  // The host selector keeps the current scientific viewer available at all times.
  const originalSelect=window.studioSelectImageStyle;
  window.studioSelectImageStyle=function(value){
    if(value!=='molart')toggle(value);
    originalSelect(value);menu.value=value;
    if(value==='molart')toggle(value);
  };
  menu.addEventListener('change',event=>{event.stopImmediatePropagation();window.studioSelectImageStyle(menu.value);},true);
  const load=window.studioLoadStructureB64;
  window.studioLoadStructureB64=function(encoded,format,name,canSelect,controls){
    ++generation;clear();payloads=[];chainStyles={};chainArt={};selectedArt=false;selectable=!!canSelect;
    const result=load(encoded,format,name,canSelect,controls);
    if(result.ok){payloads=[{encoded,format,name}];if(active)void enter();}else if(active)fail(Error(result.error));
    return result;
  };
  const trajectory=window.studioLoadTrajectoryB64;
  window.studioLoadTrajectoryB64=function(values,controls){
    ++generation;clear();payloads=[];chainStyles={};chainArt={};selectedArt=false;selectable=false;
    const result=trajectory(values,controls);
    if(result.ok){payloads=values;if(active)void enter();}else if(active)fail(Error(result.error));
    return result;
  };
  // Preserve the existing local geometry-overlay route, including automatic
  // switching to Paper pocket when an exact recorded cone is supplied.
  const geometry=window.studioSetPocketGeometryB64;
  window.studioSetPocketGeometryB64=function(encoded){if(encoded&&active)window.studioSelectImageStyle('pocket');return geometry(encoded);};
  el('molartChain').addEventListener('change',syncChainUI);
  el('molartChainStyle').addEventListener('change',()=>{
    const chain=el('molartChain').value,value=el('molartChainStyle').value;
    if(chain)chainStyles[chain]=value;else selectedStyle=value;
    applySettings();syncChainUI();
  });
  el('molartArt').addEventListener('change',()=>{const chain=el('molartChain').value;if(chain)chainArt[chain]=el('molartArt').checked;else selectedArt=el('molartArt').checked;syncChainUI();applySettings();});
  for(const id of ['molartSeed','molartDeform','molartSun','molartLight','molartFaces'])el(id).addEventListener('change',applySettings);
  el('molartFit').addEventListener('click',()=>engine?.fit(el('molartChain').value?[el('molartChain').value]:[]));
  new MutationObserver(()=>{if(active&&engine)showFrame(bridge.renderer.currentFrame);}).observe(el('frameCounter'),{childList:true,characterData:true,subtree:true});
  for(const name of ['input','change'])el('frameSlider').addEventListener(name,event=>{if(!active)return;const index=Number(event.target.value);bridge.renderer.stopAnimation();bridge.renderer.setFrame(index);showFrame(index);event.stopImmediatePropagation();},true);
  async function png(){
    if(!active||!engine||!ready||error)throw Error('No complete Molart picture to export.');
    settings();
    const token=generation, instance=engine,blob=await engine.png(Number(el('molartExportSize').value));
    if(token!==generation||engine!==instance||!ready)throw Error('The structure changed during export; export the current image again.');
    const uri=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
    if(token!==generation||engine!==instance||!ready)throw Error('The structure changed during export; export the current image again.');
    return uri;
  }
  el('saveImageButton').addEventListener('click',event=>{if(!active)return;event.preventDefault();event.stopImmediatePropagation();
    png().then(uri=>{if(window.webkit?.messageHandlers?.pocketPNG)window.webkit.messageHandlers.pocketPNG.postMessage({uri,filename:'Molart.png'});else{const a=document.createElement('a');a.download='Molart.png';a.href=uri;a.click();}}).catch(e=>note(String(e.message||e)));
  },true);
  // A synchronous thumbnail caller must never receive the hidden illustration
  // while Molart is visible. The native Save route uses the async PNG API.
  const previousPNG=window.studioPNG;
  window.studioPNG=()=>active?null:previousPNG();
  window.studioMolartPNG=png;
  window.studioMolartState=()=>({active,ready,error,style:selectedStyle,art:selectedArt,chainArt:{...chainArt},frame:frameIndex,created,disposed,selectable,info:lastInfo,engine:engine?.state()||null});
  window.studioMolartPixels=size=>engine&&ready?engine.pixels(size):null;
  window.addEventListener('pagehide',()=>{++generation;clear();});
})();
