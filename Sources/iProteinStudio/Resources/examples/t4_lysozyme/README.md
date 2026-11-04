# T4 lysozyme — 2LZM

The built-in protein example is the 164-residue, unmutated T4 lysozyme sequence
represented by [RCSB PDB 2LZM](https://www.rcsb.org/structure/2LZM), a 1.7 Å
experimental X-ray structure. Source files were retrieved from RCSB on 2026-11-04.

- `2LZM.pdb` and `2LZM.cif`: unchanged RCSB downloads, original chain A.
- `target.pdb`: protein ATOM records only; chain A renamed B for Studio's target
  role. Residue numbers, atom names and coordinates are unchanged; solvent is omitted.
- `target.fasta`: all 164 observed residues, matching the deposited polymer sequence.
- `provenance.json`: source URLs, transformations and file SHA256 digests.

Predict loads the sequence and offers the matching target PDB as its optional
structure template. Guidance is off until explicitly enabled. Query chain A is
matched by sequence to the bundled structure's chain B. RFdiffusion3 uses the
same complete target and whole-surface placement; no validated binding epitope
is implied. This is an input/example change, not a new design-performance claim.

No precomputed alignment is bundled. Existing alignments are reused when they
match; otherwise the selected alignment policy determines preparation. Offline
alignment-only requests stop if an alignment is missing. Original toxin examples
are no longer offered or shipped; saved projects and completed runs are unchanged.
