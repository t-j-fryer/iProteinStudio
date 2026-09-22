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
