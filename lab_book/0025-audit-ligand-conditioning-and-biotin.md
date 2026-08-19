---
entry: 0025
title: Audit ligand conditioning and reproduce the biotin PDB failure
date: 2026-08-18
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, ligand, ui, pdb, chemistry]
---

## Context

The RFdiffusion3 ligand form did not explain what **Suggest for me** selected,
showed atom identifiers that could not be mapped back onto the 2D molecule, and
reported no matched PDB structures for biotin. Donor/acceptor suggestions also
appeared to be absent. This audit follows [[0024-editable-numbers-richardson-and-method-matrix]].

## What was done

- Traced section 3 from `RFD3TargetInspector.suggestedConditions()` through
  `inspect_target.py` and the emitted Foundry input fields.
- Ran the inspector on the exact submitted biotin SMILES.
- Re-ran the saved biotin ligand-intelligence request from
  `~/.iproteinstudio/projects/untitled_design` against the live RCSB APIs.
- Compared the submitted molecule's full stereochemical InChIKey with every
  returned Chemical Component Dictionary candidate.
- Re-ran the complete analysis while restricting the candidate to the exact BTN
  stereoisomer.
- Checked `select_buried`, `select_hotspots`, and hydrogen-bond semantics against
  the official RosettaCommons/foundry RFdiffusion3 input documentation and
  nucleic-acid example at commit `faf42996a3cfc5f2caa726777c5745dd74c9b040`.
- Used RDKit's Lipinski atom queries to classify biotin donors and acceptors for
  the molecular graph and protonation state actually supplied.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Current strict-graph RCSB search | 1 query | candidate CCDs | A1CK6, BTN, BTQ |
| Current pipeline | 1 first candidate | PDB entries fetched / geometry matched | 1 / 0 |
| Full stereochemical identity | 3 candidates | exact candidate | BTN only |
| Correct BTN route | 30 entries | coordinate instances matched | 26 |
| Current biotin suggestion | 16 heavy atoms | H-bond suggestions | 0 |
| RDKit Lipinski classification for submitted neutral biotin | 16 heavy atoms | donors / acceptors | 3 / 3 |

The submitted InChIKey is `YBJHBAHKTGYVGT-ZKWXMUAHSA-N`, exactly matching BTN.
A1CK6 and BTQ share only the connectivity block and have different stereochemical
blocks. `confirm_identical_ccds()` compared only the connectivity block, then
`experimental_conformers()` stopped after retrieving one A1CK6 instance. The UI's
“no matches” therefore meant zero coordinate-to-cluster matches after choosing the
wrong stereoisomer, not that biotin was absent from the PDB.

The suggestion heuristic is also unsuitable for biotin. Its generic
`C(=O)N[CX4][CX4][NX3]` exposure SMARTS calls part of the bicyclic ureido core an
“aminoalkyl-amide linker.” Exposure matches take priority over hydrogen-bond
classification, so no atom receives an H-bond suggestion.

Two incompatible identifiers are exposed. Section 2 stores a zero-based RDKit
SMILES atom index (the saved request chose index 9), while section 3 displays
RFD3 atom names derived from canonical ranks on the hydrogen-added molecule
(`C22` for that same atom). Neither depiction labels the mapping.

Finally, the H-bond UI is directionally wrong. Upstream
`select_hbond_donor`/`select_hbond_acceptor` describe the selected target atom.
Studio labels them as what the designed protein should do, then writes the same
word to the target-atom field. The current help and automatic N/O rule therefore
invert the actual condition.

## Decision and rationale

Do not present the present heuristic as a safe recommendation. The fixes should:

1. annotate one shared RFD3 atom name directly on every ligand depiction and use
   it for both selection and the condition table;
2. replace attachment-atom-only splitting with an explicit attachment bond/side,
   because one atom is insufficient to determine which connected side is linker;
3. require full InChIKey equality when stereochemistry is specified, search every
   exact CCD rather than stopping at the first connectivity match, and distinguish
   “found in PDB” from “coordinates matched a computed state”;
4. make donor/acceptor labels describe the selected ligand atom, matching Foundry;
5. derive donor and acceptor atom sets from RDKit's validated feature queries for
   the supplied graph, allowing an atom to carry both when appropriate, while
   warning that a different tautomer/protonation state changes the answer; and
6. show every proposed condition and its reason on the molecule before applying it.

An atom-only linker guess was rejected because it is topologically ambiguous.
Using element plus hydrogen count as an H-bond classifier was rejected because it
misclassifies amides, charged atoms, sulfur, aromatic nitrogens, and carboxylic acids.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Sources/iProteinStudio/Resources/rfd3/inspect_target.py \
  --kind ligand \
  --smiles 'C1[C@H]2[C@@H]([C@@H](S1)CCCCC(=O)O)NC(=O)N2'

caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Sources/iProteinStudio/Resources/rfd3/ligand_intelligence.py \
  /Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3/assets/conformers/ligand_request.json
```

The exact-candidate verification temporarily overrode the search result to `BTN`
without changing repository code. Live RCSB results are time-dependent; the JSON
results quoted above were observed on 2026-08-18.

## Limits and what was not tested

- No production code was changed in this audit.
- Only biotin was used as the detailed molecule. The generic SMARTS and identifier
  bugs can affect other ligands, but their prevalence was not measured.
- RDKit feature perception is reliable for the molecular graph supplied; it does
  not determine the biologically relevant protonation or tautomer automatically.
- The RFdiffusion3 model's quantitative adherence to each condition was not
  benchmarked here; upstream semantics and input feature direction were checked.

## Next

Implement the six changes above, add biotin fixtures for stereochemical PDB identity,
atom-name mapping, linker splitting, and donor/acceptor direction, then inspect the
rebuilt GUI before allowing **Suggest for me** to be treated as a safe default.
