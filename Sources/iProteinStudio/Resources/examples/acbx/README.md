# alpha-Cobratoxin (aCbx)

A 71-residue three-finger toxin from *Naja kaouthia*. It is the worked protein
example throughout iProteinStudio: small enough to fold in a couple of minutes,
disulfide-rich enough to be a real test of a predictor, and a genuine target —
antivenom development wants binders against exactly this.

| File | What it is |
|---|---|
| `target.fasta` | the sequence |
| `target.pdb` | experimental structure for RFdiffusion3: RCSB PDB **1CTX**, chain A remapped to Studio target chain B |
| `target_msa.a3m` | **1,148 aligned sequences, already generated** |

The alignment is the point of shipping this. Generating it means a round trip to
a public MSA server that often takes longer than the fold itself, and every
example in the app would otherwise start by waiting on it. It is copied into the
shared alignment cache on first launch and indexed by the sequence it describes,
so anything you fold against aCbx — in any tab, by any engine — finds it
immediately and never asks the server.

Legacy execution-acceptance jobs used **B67, B69 and B71**. Those residues are
not a scientifically validated binder epitope, so the RFdiffusion3 worked
example now defaults to unbiased whole-surface placement.

The target geometry is the complete 71-residue, 2.8 Å X-ray structure from
1CTX (*Naja siamensis*; the sequence is identical to the example sequence). It
contains all five annotated disulfides: 3–20, 14–41, 26–30, 45–56 and 57–62.
This provenance matters because RFdiffusion3 fixes the supplied target geometry;
it does not repair a misfolded target during binder generation.
