# Bundled pipeline third-party notices

## DunbrackLab IPSAE

The numerical ipSAE implementation in `scripts/ipsae_score.py` is adapted from
DunbrackLab/IPSAE version 4.

Copyright (c) 2025 Lab of Dr. Roland Dunbrack

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Experimental PSICHIC-XL screening

PSICHIC upstream source: https://github.com/huankoh/PSICHIC, pinned commit
`cc445aa28d044c6212023705208b1a7704a00622`. Upstream source is Apache-2.0;
the portable runtime retains its LICENSE. The Studio adapter preserves the
upstream graph model and contact head and uses a validated blocking-transfer
MPS ESM batching path. Model assets are downloaded separately from their
approved upstream endpoints and are not included in Studio or runtime archives.

## ESMFold2 / ESMC MLX (optional portable runtime)

- MLX port: Fausto Milletari and contributors, <https://github.com/faustomilletari/mlx-lm>
- Pinned revision: `c26b9af872158d822a8c95589708eedd3b9c0831`
- Upstream proposal: <https://github.com/ml-explore/mlx-lm/pull/1484> (unofficial port)
- Original ESMFold2/ESMC models and CPU input/output helpers: Biohub, <https://github.com/Biohub/esm>
- MLX and MLX-LM: Apple and contributors. Port code: MIT; retained dependency licences include Transformers Apache-2.0.

The portable runtime retains upstream source and licence notices. Studio adds
orchestration and I/O adapters. Checkpoints are downloaded separately from pinned
Biohub revisions, never redistributed in the app or runtime archive. Model use
remains subject to the applicable upstream terms. See docs/ESMFOLD2.md for model
choices, measured speed scope and experimental limitations.
