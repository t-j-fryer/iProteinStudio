# Optional Molart renderer

From <https://github.com/martin-steinegger/molart> at
`a200691c2432fcb005ae2206352891b74847e64b` (MIT), using its locked Three.js0.187.0
(MIT). Full licence texts accompany this file. `UPSTREAM.json` records content
hashes and dependencies; `tools/molart/upstream-manifest.json` verifies source.

Studio bundles the upstream parser, model, geometry, style registry, renderer and
shaders with a small adapter. The website UI, fetching, samples and node tooling
are excluded from the runtime. Files are supplied locally by Studio. The shared
host `py2dmol/studio-molart.js` handles the selector, native export and lifecycles.

A narrow lifecycle-only patch retains/disconnects the upstream ResizeObserver;
the adapter disposes caches/targets and applies discrete wheel controls in
inactive WebKit windows. Scientific coordinates and upstream geometry algorithms
are unchanged. Target-aligned trajectories use a separate display-coordinate
copy; a fingerprint checks the original parsed coordinates remain unchanged.

Molart draws protein illustration, not ligand/nucleic-acid/selection/geometry
analysis. Science mode is default; reshaping drawn ribbons needs explicit Art
mode and a visible label. Existing Illustration/Paper pocket remain available.
The original Molart/Three.js authors deserve the rendering attribution; Studio
provides the native integration. See`docs/MOLART_VIEWER.md` and`tools/molart/`.
