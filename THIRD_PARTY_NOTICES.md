# Third-party notices

This inventory covers code shipped inside `iProteinStudio.app`. Optional model
engines and checkpoints are downloaded separately after the user chooses them;
they are not part of the application binary and remain under their upstream
terms.

## Sparkle 2.9.2

- Project: <https://github.com/sparkle-project/Sparkle>
- Pinned revision: `6276ba2b404829d139c45ff98427cf90e2efc59b`
- Role: application update framework
- Licence: permissive MIT-style licence plus the external notices contained in
  Sparkle's `LICENSE`

The exact upstream `LICENSE` from the pinned Swift package checkout is copied to
`Contents/Resources/ThirdPartyLicenses/Sparkle-LICENSE.txt` during every build.
Trusted distribution betas enable Sparkle with EdDSA-signed archives; local
development builds disable updates.

## py2Dmol

- Project: <https://github.com/sokrypton/py2Dmol>
- Pinned revision: `70e9b96b395d061a8b2aa9e83a10a568126eaed6`
- Role: offline protein structure renderer
- Licence: Beer-Ware licence, revision 42

The exact text is shipped as `py2Dmol-LICENSE.txt`. Studio's host adapter is an
iProteinStudio file; the upstream viewer files and local adaptations are listed
in `Sources/iProteinStudio/Resources/web/py2dmol/UPSTREAM.md`.

## RDKit MinimalLib JavaScript/WebAssembly

- Project: <https://github.com/rdkit/rdkit>
- Role: local ligand parsing, atom mapping and two-dimensional depiction
- Licence: BSD 3-Clause
- Bundled SHA-256, JavaScript:
  `58d3c996ade7e0b0137d4f9363ff6c204b545689428fa0898eeaed579ef788d9`
- Bundled SHA-256, WebAssembly:
  `e0967d44fed59e44a2d07bfc08f3a86821c54a14c95bb7e6e392fe867333b8c8`

The original import did not record an upstream release tag. The hashes above
make the present binary identifiable, but a future refresh must use a named,
pinned RDKit release and update this notice. The exact licence text is shipped
as `RDKit-LICENSE.txt`.

## 3Dmol.js

- Project: <https://github.com/3dmol/3Dmol.js>
- Role: legacy offline molecular rendering used by the ligand/thumbnail views
- Licence: BSD 3-Clause, with upstream notices for incorporated GLmol, Three.js
  and jQuery code
- Bundled SHA-256:
  `e46d1a006a87d0255b384e6bdf8e831344f2e8e0a2b34468fc125cfc5b3da00f`

The original import did not record an upstream release tag. A future refresh
must use a named, pinned release and update this notice. The complete upstream
licence and incorporated-code notices are shipped as `3Dmol-LICENSE.txt`.

## DunbrackLab IPSAE

- Project: <https://github.com/DunbrackLab/IPSAE>
- Version adapted: 4
- Role: numerical ipSAE scoring in the bundled pipeline
- Copyright: 2025 Lab of Dr. Roland Dunbrack
- Licence: MIT

The retained notice and permission text are shipped as `IPSAE-LICENSE.md` and
remain in `Sources/iProteinStudio/Resources/pipeline/THIRD_PARTY_NOTICES.md`.

## Optional downloaded software and data

The managed installer can retrieve pinned versions of Boltz, LigandMPNN,
AntiFold, IntelliFold, Protenix, LASErMPNN, OpenFold-3 MLX, RFdiffusion3 MLX,
NESSO and PSICHIC,
their Python dependencies, model checkpoints and chemical reference data.
Those payloads are stored outside the app in `~/.iproteinstudio`; they are not
redistributed in the DMG or ZIP. The shipped portable runtime catalog and model-asset manifests record immutable
archive identities, upstream revisions and download checksums. Runtime packages
retain their upstream licences and notices; model assets download separately.
The explicit source-build route also retains its upstream pins in the installer.

The ability to download an artifact does not grant additional rights to it.
Users remain responsible for the upstream licence, model licence, acceptable-use
conditions and external-service terms applicable to the components they choose.


## NESSO native-MPS adaptation (optional engine)

- Project: <https://github.com/recursionpharma/nesso>
- Source revision: `6c72f66720d9d3447fd73c515cda963e39128b1f`
- Role: experimental sequence–small-molecule affinity screening in NISE
- Licence: Apache-2.0

The version-guarded adaptation from iProteinHunter-beta and exact upstream
licence are shipped under `pipeline/scripts/nise/nesso_assets/`. Installed NESSO
retains the upstream package's additional licence notices. NESSO v1.0.0 and
ESM-2 weights are downloaded separately into the managed component directory;
no model weights are distributed with Studio. Pins and provenance are recorded
in the bundled `nesso_assets/protocol.json` and the NISE `UPSTREAM.json`.
