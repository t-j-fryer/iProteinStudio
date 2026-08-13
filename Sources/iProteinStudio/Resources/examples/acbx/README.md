# alpha-Cobratoxin (aCbx)

A 71-residue three-finger toxin from *Naja kaouthia*. It is the worked protein
example throughout iProteinStudio: small enough to fold in a couple of minutes,
disulfide-rich enough to be a real test of a predictor, and a genuine target —
antivenom development wants binders against exactly this.

| File | What it is |
|---|---|
| `target.fasta` | the sequence |
| `target.pdb` | a structure, for RFdiffusion3 (which designs against geometry, not sequence) |
| `target_msa.a3m` | **1,148 aligned sequences, already generated** |

The alignment is the point of shipping this. Generating it means a round trip to
a public MSA server that often takes longer than the fold itself, and every
example in the app would otherwise start by waiting on it. It is copied into the
shared alignment cache on first launch and indexed by the sequence it describes,
so anything you fold against aCbx — in any tab, by any engine — finds it
immediately and never asks the server.

Surface patch used in the validated design work: **B67, B69, B71**.
