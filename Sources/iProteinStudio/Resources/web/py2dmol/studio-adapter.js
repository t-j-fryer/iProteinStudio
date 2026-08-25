/* iProteinStudio adapter for the vendored py2Dmol renderer. */
(function () {
  "use strict";

  const root = document.getElementById("studioViewerRoot");
  const status = document.getElementById("studioStatus");
  initializePy2DmolViewer(root, "studio");
  const api = window.py2dmol_viewers && window.py2dmol_viewers.studio;
  const renderer = api && api.renderer;
  const objectRow = document.getElementById("objectRow");
  let suppressSelectionMessage = false;

  function report(message) {
    status.textContent = message || "";
    status.style.display = message ? "block" : "none";
    if (message && window.webkit && window.webkit.messageHandlers.viewerStatus) {
      window.webkit.messageHandlers.viewerStatus.postMessage(message);
    }
  }

  function decodeBase64(value) {
    const bytes = Uint8Array.from(atob(value), c => c.charCodeAt(0));
    return new TextDecoder("utf-8").decode(bytes);
  }

  function clearRenderer() {
    renderer.stopAnimation();
    renderer.clearResidueSelection();
    renderer.objectsData = {};
    renderer.currentObjectName = null;
    renderer.currentFrame = -1;
    renderer.coords = [];
    renderer.chains = [];
    renderer.positionTypes = [];
    if (renderer.objectSelect) renderer.objectSelect.replaceChildren();
  }

  function frameFor(model, parsed, isCIF) {
    return convertParsedToFrameData(
      model,
      isCIF ? null : parsed.modresMap,
      isCIF ? parsed.chemCompMap : null,
      false,
      isCIF ? null : parsed.conectMap,
      isCIF ? parsed.structConn : null,
      isCIF ? parsed.chemCompBondMap : null
    );
  }

  window.studioLoadStructureB64 = function (encoded, format, name, selectable, controls) {
    try {
      if (!renderer) throw new Error("py2Dmol did not initialise.");
      report("");
      root.classList.toggle("studio-compact", !controls);
      const text = decodeBase64(encoded);
      const isCIF = String(format).toLowerCase() !== "pdb";
      const parsed = isCIF ? parseCIF(text) : parsePDB(text);
      const models = parsed.models || [];
      const frames = models.map(model => frameFor(model, parsed, isCIF))
        .filter(frame => frame && frame.coords && frame.coords.length);
      if (!frames.length) throw new Error("No protein, nucleic-acid or ligand coordinates could be read.");

      suppressSelectionMessage = true;
      clearRenderer();
      const objectName = name || "structure";
      renderer.addObject(objectName);
      for (const frame of frames) renderer.addFrame(frame, objectName);
      renderer.selectionEnabled = !!selectable;
      renderer._switchToObject(objectName);
      renderer.setFrame(0);
      renderer.render("iProteinStudio load");
      // Studio loads one named object at a time. Upstream's object chooser is
      // useful in notebooks with several objects, but here it only consumes a
      // row and becomes unreadable in the narrower Target Prep viewer.
      if (objectRow) objectRow.hidden = true;
      suppressSelectionMessage = false;
      return {ok:true, frames:frames.length, positions:frames[0].coords.length};
    } catch (error) {
      suppressSelectionMessage = false;
      const message = "Could not display this structure: " + (error && error.message ? error.message : String(error));
      report(message);
      return {ok:false, error:message};
    }
  };

  window.studioSetSelection = function (residueTokens) {
    if (!renderer || !renderer.currentObjectName) return;
    const object = renderer.objectsData[renderer.currentObjectName];
    const frame = object && object.frames && object.frames[renderer.currentFrame];
    if (!frame) return;
    const wanted = new Set((residueTokens || []).map(String));
    const positions = new Set();
    (frame.residue_numbers || []).forEach((number, index) => {
      const chain = frame.chains && frame.chains[index] ? String(frame.chains[index]) : "";
      if (wanted.has(chain + String(number)) && (!frame.position_types || frame.position_types[index] === "P")) {
        positions.add(index);
      }
    });
    suppressSelectionMessage = true;
    if (positions.size) renderer.setResidueSelection(positions);
    else renderer.clearResidueSelection();
    renderer.render("iProteinStudio selection");
    suppressSelectionMessage = false;
  };

  window.studioPNG = function () {
    const canvas = root.querySelector("#canvas");
    return canvas ? canvas.toDataURL("image/png") : null;
  };

  document.addEventListener("py2dmol-residue-selection-change", function () {
    if (suppressSelectionMessage || !renderer || !renderer.currentObjectName) return;
    const object = renderer.objectsData[renderer.currentObjectName];
    const frame = object && object.frames && object.frames[renderer.currentFrame];
    if (!frame) return;
    const values = new Set();
    for (const index of (renderer.residueSelection || [])) {
      if (frame.position_types && frame.position_types[index] !== "P") continue;
      const number = frame.residue_numbers && Number(frame.residue_numbers[index]);
      const chain = frame.chains && frame.chains[index] ? String(frame.chains[index]) : "";
      if (Number.isFinite(number) && chain) values.add(chain + String(number));
    }
    const sorted = Array.from(values).sort((a, b) => a.localeCompare(b, undefined, {numeric:true}));
    if (window.webkit && window.webkit.messageHandlers.hotspots) {
      window.webkit.messageHandlers.hotspots.postMessage(JSON.stringify(sorted));
    }
  });
})();
