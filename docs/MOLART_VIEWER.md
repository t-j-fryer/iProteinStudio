# Molart protein illustrations

In a full structure viewer, use **Image style** to switch between Illustration,
Paper pocket and **Molart**. With Molart selected, **Chain style** chooses among
all 21 upstream presets, including Scientific, Glass, Frosted, Surface and the
artist-inspired styles.
This uses Martin Steinegger's [Molart](https://github.com/martin-steinegger/molart),
not Mol*. It is bundled locally; selecting it does not open a website, fetch a
PDB or upload your structure. No extra software or engine installation is needed.

Molart draws protein ribbons or its own Gaussian protein surface. It does not
show ligands, nucleic acids, residue/atom selection highlights or recorded exit
cones. Use Illustration or Paper pocket for those features. Recorded cone inspection switches back to Paper pocket. The image is
a display, not an independent structural assessment or a new hit filter.

Drag to rotate, scroll to zoom and right-drag to pan. **Apply to** chooses all
protein chains or one chain for its style and Science/Art mode; **Fit view** fits
that choice. Illustration seed controls deterministic display effects and is
unrelated to model seeds. Sun controls enable cast shadows and light direction.
Use **Save PNG** with 1024, 2048 or 4096 square-pixel output.

Science mode is the default. **Art mode** is an explicit opt-in that may reshape
the drawn ribbon; an orange label stays visible whenever any chain uses it.
Source coordinates, files, scores and verdicts remain unchanged. A newly loaded
structure clears art mode and per-chain choices. Molart's own secondary-structure
assignment and stylized ribbon widths can differ from other renderers; do not use
an artistic image to measure contacts or infer a changed protein conformation.

For result trajectories, cycle scrubbing uses the existing target alignment on
chains B onward. Only a separate display-coordinate copy is aligned; the source
coordinates remain immutable. Playback and frame overlays stay in Illustration.
The selector releases Molart's canvas/GPU caches on exit and creates it lazily,
so compact results do not each acquire another renderer. Invalid or unsupported
inputs clear the previous Molart scene and disable export instead of leaving an
old protein visible.

Upstream revision, Three.js version, licence texts and bundle hashes are shipped
under `web/molart/`. [Build instructions](../tools/molart/README.md) describe the
pinned source/lockfile check and narrow native-lifecycle adaptations. End users
need neither Node nor npm. Available in public 0.2.45/build105 and Beta104.

The viewer keeps routine style descriptions, residue/chain counts, parser notes
and attribution out of the control panel. Licence/author information remains
in the bundled notices and this documentation. Only loading/actionable errors
and the short Art mode warning appear when relevant.
