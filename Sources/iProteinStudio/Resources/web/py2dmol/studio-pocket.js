/* Studio's offline surface image style. Upstream py2Dmol stays unmodified. */
(function () {
  'use strict';
  const byID = id => document.getElementById(id);
  const root = byID('studioViewerRoot'), panel = byID('pocketPanel');
  const bridge = window.studioSurfaceBridge, illustration = bridge.renderer;
  const style = byID('imageStyle'), ligandSelect = byID('pocketLigand');
  let viewer, library, models = [], payloads = [], trajectory = false, selectable = false;
  let active = false, frameIndex = -1, selected = new Set(), geometry = null;
  let revision = 0, timer, surfaces = [], ready = false, error = '', rotation = '';
  let drawing=Promise.resolve(), loadRevision=0;
  let lastAction='initial';
  let currentSurfaceStyle={};
  let oldControls = [], oldRotate = false;
  const number = id => Number(byID(id).value);
  const decode = encoded => new TextDecoder().decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0)));
  const key = atom => JSON.stringify([atom.chain || '', atom.resi, atom.icode || '', atom.resn || '']);
  const note = text => { byID('pocketNote').textContent = text; };

  function ensureLibrary() {
    if (window.$3Dmol) return Promise.resolve();
    if (!library) library = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '../mol/3Dmol-min.js';
      script.onload = resolve;
      script.onerror = () => reject(new Error('The bundled surface renderer could not be loaded.'));
      document.head.appendChild(script);
    });
    return library;
  }
  function targetAtoms(model) {
    const result = new Map();
    for (const a of model.selectedAtoms({atom:'CA', hetflag:false})) {
      if (a.chain && a.chain !== 'A') result.set(a.chain + ':' + a.resi, [a.x,a.y,a.z]);
    }
    return result;
  }
  function alignModels() {
    if (!trajectory || models.length < 2) return;
    const frames=illustration.objectsData[illustration.currentObjectName].frames;
    for (let index=1;index<models.length;index++) {
      const model=models[index], frame=frames[index], reference=new Map();
      frame.coords.forEach((position,i) => {
        if (frame.position_types[i]==='P' && frame.chains[i] && frame.chains[i]!=='A') {
          reference.set(frame.chains[i]+':'+frame.residue_numbers[i],position);
        }
      });
      const moving = targetAtoms(model), keys = [...reference.keys()].filter(k => moving.has(k));
      if (keys.length < 3) throw new Error('Pocket trajectory needs three common target Cα atoms on chains B onward.');
      const atoms = model.selectedAtoms({});
      const aligned = bridge.rigidlyAlignCoordinates(atoms.map(a => [a.x,a.y,a.z]),
        keys.map(k => moving.get(k)), keys.map(k => reference.get(k)));
      atoms.forEach((a,i) => { [a.x,a.y,a.z] = aligned[i]; });
    }
  }
  function groups() {
    const result = new Map();
    const model = models[frameIndex];
    if (!model) return result;
    for (const atom of model.selectedAtoms({hetflag:true})) {
      if (['HOH','WAT','DOD'].includes(atom.resn)) continue;
      if (!result.has(key(atom))) result.set(key(atom), []);
      result.get(key(atom)).push(atom);
    }
    return new Map([...result].filter(([,atoms]) => atoms.length > 1));
  }
  function selectedLigand() { return groups().get(ligandSelect.value) || []; }
  function atomSelection(atoms) {
    return {model:models[frameIndex].getID(), index:atoms.map(a => a.index)};
  }
  function centre(atoms) {
    return ['x','y','z'].map(axis => atoms.reduce((sum,a) => sum + a[axis], 0) / atoms.length);
  }
  function viewDepth(atom, origin) {
    const [qx,qy,qz,qw] = viewer.getView().slice(4);
    const x=atom.x-origin[0], y=atom.y-origin[1], z=atom.z-origin[2];
    return 2*(qx*qz-qy*qw)*x + 2*(qy*qz+qx*qw)*y + (1-2*(qx*qx+qy*qy))*z;
  }
  function distance(atom, ligand) {
    return Math.sqrt(Math.min(...ligand.map(a => (a.x-atom.x)**2+(a.y-atom.y)**2+(a.z-atom.z)**2)));
  }
  function shade(fade) {
    const base=[184,191,197];
    return new $3Dmol.Color((Math.round(base[0]+(255-base[0])*fade)<<16)
      | (Math.round(base[1]+(255-base[1])*fade)<<8) | Math.round(base[2]+(255-base[2])*fade));
  }
  function labelValues() {
    byID('pocketRadiusValue').value = number('pocketRadius') + ' Å';
    byID('pocketOpacityValue').value = Math.round(number('pocketOpacity')*100) + '%';
    byID('pocketDepthValue').value = number('pocketDepth') + ' Å';
    byID('pocketFadeValue').value = number('pocketFade') + ' Å';
  }
  function decorate() {
    if (!viewer || frameIndex < 0) return;
    viewer.removeAllShapes();
    const model = models[frameIndex], ligand = selectedLigand();
    viewer.setStyle({}, {});
    if (selectable) model.setStyle({hetflag:false}, {stick:{color:'#b8bfc5',radius:0.04,opacity:0.05}});
    if (ligand.length) model.setStyle({index:ligand.map(a => a.index)},
      {stick:{color:'#e6ad3c',radius:0.14},sphere:{color:'#e6ad3c',scale:0.23}});
    const chosen = model.selectedAtoms({hetflag:false}).filter(a => selected.has((a.chain || '')+a.resi));
    if (chosen.length) model.setStyle({index:chosen.map(a => a.index)}, {stick:{color:'#c93145',radius:0.2}});
    model.setClickable({hetflag:false}, selectable, atom => {
      const token = (atom.chain || '') + atom.resi;
      if (selected.has(token)) selected.delete(token); else selected.add(token);
      window.studioSetSelection([...selected]);
      if (window.webkit?.messageHandlers?.hotspots) {
        window.webkit.messageHandlers.hotspots.postMessage(JSON.stringify([...selected].sort()));
      }
    });
    const showCone = geometry?.cone && byID('pocketCone').checked && models.length===1
      && ligand.some(a => a.chain === (geometry.ligand_chain || 'B'));
    byID('pocketConeRow').hidden = !geometry?.cone || models.length!==1;
    byID('pocketConeLegend').hidden = !showCone;
    if (showCone) {
      const point = a => ({x:a[0],y:a[1],z:a[2]});
      const cone = geometry.cone;
      for (let i=1;i<cone.stem.length;i++) viewer.addCylinder({start:point(cone.stem[i-1]),end:point(cone.stem[i]),radius:.065,color:'#0d8fa6'});
      cone.stubs.forEach((stub,i) => {
        const color={wide:'#0d9488',limited:'#e5a13b',clash:'#dc5360'}[cone.labels[i]];
        viewer.addCylinder({start:point(stub[1]),end:point(stub[2]),radius:.035,color});
        viewer.addSphere({center:point(stub[2]),radius:.075,color});
      });
    }
    viewer.render();
  }
  async function drawSurface(token) {
    if (!active || !viewer || frameIndex < 0 || token!==revision) return;
    lastAction='surface '+token;
    const model=models[frameIndex], ligand=selectedLigand();
    ready=false; error=''; byID('saveImageButton').disabled=true;
    for (const id of surfaces) if (viewer.getSurface(id)) viewer.removeSurface(id);
    surfaces=[];
    const polymer=model.selectedAtoms({hetflag:false});
    const local=ligand.length && byID('pocketRegion').value==='pocket';
    const cut=ligand.length && byID('pocketCutaway').checked;
    const origin=centre(ligand.length ? ligand : polymer.length ? polymer : model.selectedAtoms({}));
    const radius=number('pocketRadius'), depth=number('pocketDepth'), fade=number('pocketFade');
    const shown=polymer.filter(a => (!local || distance(a,ligand)<=radius) && (!cut || viewDepth(a,origin)<=depth));
    const control = byID('pocketRegion'); control.disabled=!ligand.length;
    byID('pocketRadius').disabled=!local;
    byID('pocketCutaway').disabled=!ligand.length;
    note(polymer.length ? 'Building molecular surface…' : 'No polymer found; displaying ligand atoms only.');
    decorate();
    try {
      if (shown.length) {
        // allsel is the COMPLETE polymer. Restrict only the displayed patches,
        // so a pocket view cannot invent a new surface around a cropped fragment.
        currentSurfaceStyle={opacity:number('pocketOpacity'), colorfunc:a => {
            const edge = local ? Math.max(0,Math.min(1,(distance(a,ligand)-(radius-2))/2)) : 0;
            const front = cut && fade>0 ? Math.max(0,Math.min(1,(viewDepth(a,origin)-(depth-fade))/fade)) : 0;
            return shade(Math.max(edge,front));
          }};
        const task=viewer.addSurface($3Dmol.SurfaceType.SES,currentSurfaceStyle,atomSelection(shown),atomSelection(polymer));
        const id=await task;
        if (token!==revision || !active) { if (viewer.getSurface(id)) viewer.removeSurface(id); return; }
        surfaces=[id];
      }
      if (token!==revision || !active) return;
      ready=true; byID('saveImageButton').disabled=false;
      lastAction='ready '+token;
      byID('pocketCanvas').style.visibility='visible';
      note(!polymer.length ? 'No polymer found; ligand atoms only.' : !ligand.length
        ? groups().size ? 'Choose a ligand to focus its pocket. Showing the whole polymer surface.'
          : 'No multi-atom ligand found. Showing the whole polymer surface.' : !shown.length
        ? 'No surface patches in this view. Increase radius or cutaway depth.'
        : 'Surface calculated from the complete polymer. Cutaway edges fade towards white.');
      viewer.render();
    } catch (failure) {
      if (token!==revision) return;
      error=String(failure?.message || failure);note('Surface could not be drawn: '+error);
    }
  }
  function surface() {
    const token=++revision;
    drawing=drawing.catch(() => {}).then(() => drawSurface(token));
    return drawing;
  }
  function schedule() { lastAction='scheduled';ready=false;clearTimeout(timer);timer=setTimeout(surface,180); }
  function fit(resetRotation=false) {
    if (!viewer || frameIndex<0) return;
    if (resetRotation) viewer.setView([...viewer.getView().slice(0,4),0,0,0,1]);
    const ligand=selectedLigand();
    const local=ligand.length && byID('pocketRegion').value==='pocket';
    viewer.zoomTo(local ? atomSelection(ligand) : {model:models[frameIndex].getID()});
    viewer.zoom(local ? .6*7/number('pocketRadius') : .85);viewer.render();schedule();
  }
  function showFrame(index, refit=false) {
    if (!viewer || !models.length) return;
    if (active) ['playButton','speedButton','overlayButton'].forEach(id => {byID(id).disabled=true;});
    const next=Math.max(0,Math.min(models.length-1,index));
    if (next===frameIndex && !refit) return;
    byID('pocketCanvas').style.visibility='hidden';
    ++revision;frameIndex=next;
    models.forEach((m,i) => i===frameIndex ? m.show() : m.hide());
    const previous=ligandSelect.value;ligandSelect.replaceChildren();
    if (groups().size>1) ligandSelect.add(new Option('Choose ligand…',''));
    for (const [value,atoms] of groups()) {
      const atom=atoms[0], option=document.createElement('option');option.value=value;
      option.textContent=(atom.resn || 'Ligand')+' · '+(atom.chain || 'unlabelled')+':'+atom.resi+(atom.icode || '');
      ligandSelect.appendChild(option);
    }
    if ([...ligandSelect.options].some(o => o.value===previous)) ligandSelect.value=previous;
    const recorded=[...groups()].filter(([,atoms]) => atoms[0].chain===(geometry?.ligand_chain || 'B'));
    if (geometry?.cone && recorded.length===1) ligandSelect.value=recorded[0][0];
    if (!ligandSelect.options.length) { const o=new Option('No ligand','');ligandSelect.add(o); }
    ligandSelect.disabled=!groups().size;
    decorate(); if (refit) fit(); else schedule();
  }
  async function loadModels() {
    const current=++loadRevision;
    lastAction='loading '+current;
    if (!payloads.length) {note('Load a structure to view its pocket.');return;}
    await ensureLibrary();
    await drawing.catch(() => {});
    if (!active || current!==loadRevision) return;
    if (!viewer) {
      viewer=$3Dmol.createViewer(byID('pocketCanvas'),{backgroundColor:'white',antialias:true});
      viewer.setProjection('orthographic');
      viewer.setViewChangeCallback(() => {
        const next=viewer.getView().slice(4).join(',');
        if (next!==rotation) { rotation=next; if (byID('pocketCutaway').checked) schedule(); }
      });
      new ResizeObserver(() => { if (active) { viewer.resize();viewer.render(); } }).observe(byID('pocketCanvas'));
    }
    viewer.clear();surfaces=[];models=[];frameIndex=-1;
    for (const payload of payloads) {
      const loaded=viewer.addModels(decode(payload.encoded),payload.format);
      if (trajectory) {
        if (!loaded.length) throw new Error('A cycle structure has no readable atoms.');
        models.push(loaded[0]);loaded.slice(1).forEach(m => viewer.removeModel(m));
      } else models.push(...loaded);
    }
    const object=illustration.objectsData[illustration.currentObjectName];
    if (!object || object.frames.length!==models.length) throw new Error('The two image styles read different frame counts; pocket display was stopped.');
    alignModels();viewer.resize();showFrame(illustration.currentFrame,true);
  }
  async function activate(value) {
    const entering=value==='pocket';
    if (entering===active) return;
    active=entering;style.value=value;panel.hidden=!entering;root.classList.toggle('studio-pocket',entering);
    if (entering) {
      oldRotate=illustration.autoRotate;
      illustration.autoRotate=false;if (illustration.rotationCheckbox) illustration.rotationCheckbox.checked=false;
      if (illustration.isPlaying) illustration.togglePlay();
      oldControls=['playButton','speedButton','overlayButton'].map(id => [byID(id),byID(id).disabled,byID(id).title]);
      oldControls.forEach(([control]) => { control.disabled=true;control.title='Use Illustration for playback or frame overlays; Paper pocket supports cycle scrubbing.'; });
      byID('saveImageButton').textContent='Save PNG';
      try { await loadModels(); } catch (failure) { error=String(failure?.message || failure);note(error); }
    } else {
      ++revision;clearTimeout(timer);
      oldControls.forEach(([control,disabled,title]) => { control.disabled=disabled;control.title=title; });oldControls=[];
      illustration.updateUIControls();
      illustration.autoRotate=oldRotate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (illustration.rotationCheckbox) illustration.rotationCheckbox.checked=illustration.autoRotate;
      byID('saveImageButton').textContent='Save';byID('saveImageButton').disabled=false;
      illustration.render('iProteinStudio image style');
    }
  }
  const originalLoad=window.studioLoadStructureB64;
  window.studioLoadStructureB64=function(encoded,format,name,canSelect,controls) {
    ++revision;++loadRevision;clearTimeout(timer);ready=false;geometry=null;selected.clear();payloads=[];surfaces=[];models=[];frameIndex=-1;
    byID('pocketCanvas').style.visibility='hidden';
    const result=originalLoad(encoded,format,name,canSelect,controls);
    if (result.ok) { payloads=[{encoded,format}];trajectory=false;selectable=!!canSelect;if (active) loadModels().catch(e => note(String(e))); }
    else { error=result.error;byID('saveImageButton').disabled=active; }
    return result;
  };
  const originalTrajectory=window.studioLoadTrajectoryB64;
  window.studioLoadTrajectoryB64=function(values,controls) {
    ++revision;++loadRevision;clearTimeout(timer);ready=false;geometry=null;selected.clear();payloads=[];surfaces=[];models=[];frameIndex=-1;
    byID('pocketCanvas').style.visibility='hidden';
    const result=originalTrajectory(values,controls);
    if (result.ok) { payloads=values;trajectory=true;selectable=false;if (active) loadModels().catch(e => note(String(e))); }
    else { error=result.error;byID('saveImageButton').disabled=active; }
    return result;
  };
  const originalSelection=window.studioSetSelection;
  window.studioSetSelection=function(values) { selected=new Set(values || []);originalSelection(values);if (active) decorate(); };
  const originalPNG=window.studioPNG;
  window.studioPNG=function() { return active ? viewer && ready ? viewer.pngURI() : null : originalPNG(); };
  window.studioSetPocketGeometryB64=function(encoded) {
    geometry=encoded ? JSON.parse(decode(encoded)) : null;
    byID('pocketCone').checked=true;
    if (geometry?.cone && !active) activate('pocket');
    else if (active) {
      const matches=[...groups()].filter(([,atoms]) => atoms[0].chain===(geometry?.ligand_chain || 'B'));
      if (geometry?.cone && matches.length===1) ligandSelect.value=matches[0][0];
      decorate();schedule();
    }
  };
  window.studioSelectImageStyle=activate;
  window.studioPocketState=() => ({active,ready,error,frame:frameIndex,models:models.length,surfaces:surfaces.length,
    lastAction,revision,ligandCount:groups().size,ligandCentre:selectedLigand().length ? centre(selectedLigand()) : null,
    selected:[...selected],view:viewer?.getView(),coordinates:models.map(m => m.selectedAtoms({}).map(a => [a.x,a.y,a.z]))});
  style.addEventListener('change',() => activate(style.value));
  for (const id of ['pocketRegion','pocketRadius','pocketDepth','pocketFade','pocketCutaway']) {
    byID(id).addEventListener('input',() => { labelValues();schedule(); });
  }
  byID('pocketOpacity').addEventListener('input',() => {
    labelValues();if (viewer) {for (const id of surfaces) viewer.setSurfaceMaterialStyle(id,{...currentSurfaceStyle,opacity:number('pocketOpacity')});viewer.render();}
  });
  ligandSelect.addEventListener('change',() => {decorate();fit();});
  byID('pocketCone').addEventListener('change',decorate);byID('pocketFit').addEventListener('click',() => fit(true));
  new MutationObserver(() => { if (active) showFrame(illustration.currentFrame); }).observe(byID('frameCounter'),{childList:true,characterData:true,subtree:true});
  // Capture the requested index BEFORE stopAnimation updates the upstream UI.
  // This also makes keyboard and accessibility scrubbing work without a drag.
  for (const eventName of ['input','change']) byID('frameSlider').addEventListener(eventName,event => {
    if (!active) return;
    const index=Number(event.target.value);
    illustration.stopAnimation();illustration.setFrame(index);showFrame(index);
    event.stopImmediatePropagation();
  },true);
  byID('saveImageButton').addEventListener('click',event => {
    if (!active) return;
    event.preventDefault();event.stopImmediatePropagation();if (!ready) return;
    const uri=window.studioPNG();
    if (window.webkit?.messageHandlers?.pocketPNG) window.webkit.messageHandlers.pocketPNG.postMessage(uri);
    else {const a=document.createElement('a');a.download='Pocket.png';a.href=uri;a.click();}
  },true);
  labelValues();
})();
