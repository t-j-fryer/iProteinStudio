/* iProteinStudio adapter for the vendored py2Dmol renderer. */
(function () {
  "use strict";

  const root = document.getElementById("studioViewerRoot");
  const status = document.getElementById("studioStatus");
  initializePy2DmolViewer(root, "studio");
  const api = window.py2dmol_viewers && window.py2dmol_viewers.studio;
  const renderer = api && api.renderer;
  const objectRow = document.getElementById("objectRow");
  const frameSlider = document.getElementById("frameSlider");
  const frameCounter = document.getElementById("frameCounter");
  let suppressSelectionMessage = false;
  let trajectoryLabels = [];

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

  function parsedFrames(payload) {
    const text = decodeBase64(payload.encoded);
    const isCIF = String(payload.format).toLowerCase() !== "pdb";
    const parsed = isCIF ? parseCIF(text) : parsePDB(text);
    return (parsed.models || []).map(model => frameFor(model, parsed, isCIF))
      .filter(frame => frame && frame.coords && frame.coords.length);
  }

  function targetCoordinateMap(frame) {
    const result = new Map();
    const chains = frame.chains || [];
    const types = frame.position_types || [];
    const numbers = frame.residue_numbers || [];
    for (let index = 0; index < frame.coords.length; index++) {
      const chain = String(chains[index] || "");
      if (!chain || chain === "A" || types[index] !== "P") continue;
      result.set(`${chain}:${numbers[index]}`, frame.coords[index]);
    }
    return result;
  }

  // Horn's quaternion solution to the least-squares rigid-body fit. Keep this
  // local and dependency-free: utils.js's historical Kabsch helper expects a
  // notebook-global `numeric` object that the vendored browser bundle does not
  // export. A symmetric Jacobi eigensolver is exact enough for a 4x4 matrix and
  // avoids silently falling back to an unaligned trajectory.
  function rigidlyAlignCoordinates(fullCoordinates, moving, reference) {
    const mean = coordinates => {
      const value = [0, 0, 0];
      for (const coordinate of coordinates) {
        value[0] += coordinate[0]; value[1] += coordinate[1]; value[2] += coordinate[2];
      }
      return value.map(component => component / coordinates.length);
    };
    const movingMean = mean(moving), referenceMean = mean(reference);
    const covariance = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (let index = 0; index < moving.length; index++) {
      const p = moving[index].map((value, axis) => value - movingMean[axis]);
      const q = reference[index].map((value, axis) => value - referenceMean[axis]);
      for (let row = 0; row < 3; row++) {
        for (let column = 0; column < 3; column++) {
          covariance[row][column] += p[row] * q[column];
        }
      }
    }
    const [[sxx, sxy, sxz], [syx, syy, syz], [szx, szy, szz]] = covariance;
    const matrix = [
      [sxx + syy + szz, syz - szy, szx - sxz, sxy - syx],
      [syz - szy, sxx - syy - szz, sxy + syx, szx + sxz],
      [szx - sxz, sxy + syx, -sxx + syy - szz, syz + szy],
      [sxy - syx, szx + sxz, syz + szy, -sxx - syy + szz]
    ];
    const vectors = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
    for (let sweep = 0; sweep < 80; sweep++) {
      let p = 0, q = 1, maximum = Math.abs(matrix[p][q]);
      for (let row = 0; row < 4; row++) {
        for (let column = row + 1; column < 4; column++) {
          const value = Math.abs(matrix[row][column]);
          if (value > maximum) { maximum = value; p = row; q = column; }
        }
      }
      if (maximum < 1e-12) break;
      const angle = 0.5 * Math.atan2(2 * matrix[p][q], matrix[q][q] - matrix[p][p]);
      const cosine = Math.cos(angle), sine = Math.sin(angle);
      for (let index = 0; index < 4; index++) {
        if (index === p || index === q) continue;
        const aip = matrix[index][p], aiq = matrix[index][q];
        matrix[index][p] = matrix[p][index] = cosine * aip - sine * aiq;
        matrix[index][q] = matrix[q][index] = sine * aip + cosine * aiq;
      }
      const app = matrix[p][p], aqq = matrix[q][q], apq = matrix[p][q];
      matrix[p][p] = cosine * cosine * app - 2 * sine * cosine * apq + sine * sine * aqq;
      matrix[q][q] = sine * sine * app + 2 * sine * cosine * apq + cosine * cosine * aqq;
      matrix[p][q] = matrix[q][p] = 0;
      for (let row = 0; row < 4; row++) {
        const vip = vectors[row][p], viq = vectors[row][q];
        vectors[row][p] = cosine * vip - sine * viq;
        vectors[row][q] = sine * vip + cosine * viq;
      }
    }
    let best = 0;
    for (let index = 1; index < 4; index++) {
      if (matrix[index][index] > matrix[best][best]) best = index;
    }
    let [w, x, y, z] = vectors.map(row => row[best]);
    const norm = Math.hypot(w, x, y, z);
    w /= norm; x /= norm; y /= norm; z /= norm;
    const rotation = [
      [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]
    ];
    return fullCoordinates.map(coordinate => {
      const centered = coordinate.map((value, axis) => value - movingMean[axis]);
      return rotation.map((row, axis) =>
        row[0] * centered[0] + row[1] * centered[1] + row[2] * centered[2]
          + referenceMean[axis]);
    });
  }

  // Bounded diagnostic used by the native WebKit contract harness. It tests
  // the exact same fit routine without exposing file-system or renderer state.
  window.studioRigidFitMaximumDeviation = function (moving, reference) {
    const aligned = rigidlyAlignCoordinates(moving, moving, reference);
    return Math.max(...aligned.map((coordinate, index) => Math.hypot(
      coordinate[0] - reference[index][0], coordinate[1] - reference[index][1],
      coordinate[2] - reference[index][2])));
  };

  function alignFrameTargetToReference(frame, referenceTarget, label) {
    const movingTarget = targetCoordinateMap(frame);
    const keys = Array.from(referenceTarget.keys()).filter(key => movingTarget.has(key));
    if (keys.length < 3) {
      throw new Error(`${label} has fewer than three target Cα atoms in common with cycle 0; trajectory alignment was refused.`);
    }
    const beforeSquared = keys.map(key => {
      const a = movingTarget.get(key), b = referenceTarget.get(key);
      return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
    });
    frame.coords = rigidlyAlignCoordinates(frame.coords,
      keys.map(key => movingTarget.get(key)), keys.map(key => referenceTarget.get(key)));
    const alignedTarget = targetCoordinateMap(frame);
    const afterSquared = keys.map(key => {
      const a = alignedTarget.get(key), b = referenceTarget.get(key);
      return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
    });
    return {
      maximum: Math.sqrt(Math.max(...afterSquared)),
      beforeRMSD: Math.sqrt(beforeSquared.reduce((sum, value) => sum + value, 0) / keys.length),
      afterRMSD: Math.sqrt(afterSquared.reduce((sum, value) => sum + value, 0) / keys.length)
    };
  }

  function syncTrajectoryCounter() {
    if (!trajectoryLabels.length || !frameSlider || !frameCounter) return;
    const index = Math.max(0, Math.min(trajectoryLabels.length - 1,
      Number.parseInt(frameSlider.value || "0", 10)));
    const expected = `${trajectoryLabels[index]} · ${index + 1} / ${trajectoryLabels.length}`;
    if (frameCounter.textContent !== expected) frameCounter.textContent = expected;
  }

  if (frameSlider) {
    frameSlider.addEventListener("input", () => queueMicrotask(syncTrajectoryCounter));
    frameSlider.addEventListener("change", () => queueMicrotask(syncTrajectoryCounter));
  }
  if (frameCounter) {
    new MutationObserver(() => syncTrajectoryCounter())
      .observe(frameCounter, {childList: true, characterData: true, subtree: true});
  }

  window.studioLoadStructureB64 = function (encoded, format, name, selectable, controls) {
    try {
      if (!renderer) throw new Error("py2Dmol did not initialise.");
      report("");
      trajectoryLabels = [];
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

  window.studioLoadTrajectoryB64 = function (payloads, controls) {
    try {
      if (!renderer) throw new Error("py2Dmol did not initialise.");
      if (!Array.isArray(payloads) || payloads.length < 2) {
        throw new Error("A trajectory requires at least two complete cycle structures.");
      }
      report("");
      root.classList.toggle("studio-compact", !controls);
      const frames = payloads.map((payload, index) => {
        const candidates = parsedFrames(payload);
        if (!candidates.length) throw new Error(`${payload.name || `Frame ${index + 1}`} has no readable coordinates.`);
        return candidates[0];
      });
      const referenceTarget = targetCoordinateMap(frames[0]);
      if (referenceTarget.size < 3) {
        throw new Error("Cycle 0 has fewer than three target Cα atoms on chains B onward; trajectory alignment was refused.");
      }
      let maximumTargetDeviation = 0;
      let maximumTargetRMSD = 0;
      let alignmentImproved = true;
      for (let index = 1; index < frames.length; index++) {
        const fit = alignFrameTargetToReference(frames[index], referenceTarget,
          payloads[index].name || `Frame ${index + 1}`);
        maximumTargetDeviation = Math.max(maximumTargetDeviation, fit.maximum);
        maximumTargetRMSD = Math.max(maximumTargetRMSD, fit.afterRMSD);
        alignmentImproved = alignmentImproved && fit.afterRMSD <= fit.beforeRMSD + 1e-9;
      }

      suppressSelectionMessage = true;
      clearRenderer();
      const objectName = "Iterative design trajectory";
      renderer.addObject(objectName);
      for (const frame of frames) renderer.addFrame(frame, objectName);
      renderer.selectionEnabled = false;
      renderer._switchToObject(objectName);
      renderer.setFrame(0);
      renderer.render("iProteinStudio target-aligned trajectory");
      if (objectRow) objectRow.hidden = true;
      trajectoryLabels = payloads.map((payload, index) => payload.name || `Frame ${index + 1}`);
      queueMicrotask(syncTrajectoryCounter);
      suppressSelectionMessage = false;
      return {ok:true, frames:frames.length, targetPositions:referenceTarget.size,
        maximumTargetDeviation:maximumTargetDeviation,
        maximumTargetRMSD:maximumTargetRMSD, alignmentImproved:alignmentImproved};
    } catch (error) {
      suppressSelectionMessage = false;
      trajectoryLabels = [];
      const message = "Could not display this trajectory: "
        + (error && error.message ? error.message : String(error));
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
