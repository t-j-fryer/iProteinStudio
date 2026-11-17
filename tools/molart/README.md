# Build the optional Molart renderer

The app ships static local JavaScript; Node/npm are build tools only. Upstream
Molart is pinned at `a200691c2432fcb005ae2206352891b74847e64b`, MIT licensed.
Three.js0.187.0 is pinned by the upstream lockfile. Both licences ship beside the
bundle. `upstream-manifest.json` verifies the full source/lock/license set before
building; `UPSTREAM.json` records the resulting bundle and Studio adapter hashes.

From the repository root, with Node22+ and npm:

```bash
mkdir -p build/vendor/molart-a200691
curl -fL https://api.github.com/repos/martin-steinegger/molart/tarball/a200691c2432fcb005ae2206352891b74847e64b -o /tmp/molart.tar.gz
tar -xzf /tmp/molart.tar.gz -C build/vendor/molart-a200691 --strip-components=1
npm ci --ignore-scripts --no-audit --no-fund --prefix build/vendor/molart-a200691
npm test --prefix build/vendor/molart-a200691
node tools/molart/build.mjs build/vendor/molart-a200691 Sources/iProteinStudio/Resources/web/molart
bash Tests/test_molart_viewer.sh
```

The port imports upstream parsers, model, geometry, all21styles, shaders and
renderer. It does not use the upstream website, remote fetching, sample files or
its file-open controls. The Studio entry point supplies an existing saved pose,
explicit display settings and native PNG delivery. One narrow renderer lifecycle
patch retains/disconnects its ResizeObserver; disposal additionally frees cached
WebGL resources. A wheel handler applies discrete controls immediately when
WebKit throttles background animation. These changes do not alter the source
coordinates, style geometry algorithms or scientific outputs. For trajectories,
only a separate display-coordinate copy receives the existing Studio target
alignment; source-coordinate fingerprints remain unchanged.
