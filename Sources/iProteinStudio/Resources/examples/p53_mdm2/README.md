# p53–MDM2 RFdiffusion3 examples

`1YCR.pdb` is a protein-only copy of the RCSB Protein Data Bank entry 1YCR
(Kussie *et al.*, *Science* 1996, DOI: 10.1126/science.274.5289.948), accessed
2026-09-02. It contains observed MDM2 residues A25–109 and the bound p53
peptide residues B17–29.

iProteinStudio uses the same complex in two deliberately small worked examples:

- **Partial diffusion:** perturb p53 chain B at `partial_t = 1.0 Å` while fixing
  every MDM2 atom.
- **Motif scaffolding:** generate a 70-residue binder around p53 F19, W23 and
  L26. Those three side chains form the canonical recognition triad in the MDM2
  cleft and the p53–MDM2 case was experimentally validated in the original
  RFdiffusion work (Watson *et al.*, *Nature* 2023,
  DOI: 10.1038/s41586-023-06415-8).

The motif example fixes explicit orientation-defining side-chain atoms rather
than every motif atom. The generated source→design residue map, fixed atom list,
generation insertion RMSD and independent-prediction motif RMSD are retained in
the campaign outputs.

No model weights or generated results are bundled here. Protein Structure data
are provided by RCSB PDB under its published usage policy:
https://www.rcsb.org/pages/policies.
