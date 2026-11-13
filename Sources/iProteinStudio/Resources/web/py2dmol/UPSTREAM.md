# py2Dmol renderer

Vendored from <https://github.com/sokrypton/py2Dmol> commit
`70e9b96b395d061a8b2aa9e83a10a568126eaed6` (2026-08-18 checkout).

Included upstream files:

- `viewer.html` (adapted for iProteinStudio's responsive WebKit host)
- `viewer-mol.min.js`
- `viewer-cartoon.min.js`
- `utils.js`
- `LICENSE`

`studio-adapter.js` is an iProteinStudio file. It connects raw PDB/mmCIF input,
residue selection and PNG snapshots to the upstream renderer without any network
dependency.

`studio-pocket.js` is a Studio extension that adds the optional Paper pocket
image style through the separately bundled 3Dmol.js renderer. Its native SES
surface uses the complete polymer; pocket/camera cutaway controls select display
patches and fade edge colours towards white. It does not replace the paper's
ChimeraX per-vertex alpha renderer or alter any scientific inputs or hit criteria.
The upstream minified renderer files remain unchanged.
