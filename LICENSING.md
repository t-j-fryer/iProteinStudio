# Licensing status

This document separates three questions that must not be conflated: the licence
for original iProteinStudio code, the terms of software embedded in the app, and
the terms of scientific engines downloaded after installation.

## Original iProteinStudio code

No open-source or commercial licence is currently granted for the original
iProteinStudio code. The project was developed in an MIT research context, so
the authors should not assert an individual copyright owner or apply an
irreversible public licence before institutional review.

MIT's software disclosure instructions require all authors and embedded or
integrated third-party materials to be identified. If the authors request an
open-source release, MIT describes review culminating in a Letter for Open
Source. The next release action is therefore to submit the software copyright
disclosure and this repository's third-party inventory to the relevant MIT
Technology Licensing Officer.

Until that review is complete, unsigned artifacts produced by
`release/release_app.sh --unsigned-beta` are for controlled evaluation and
cross-Mac acceptance, not a general public release. This is intentionally more
conservative than silently choosing BSD, MIT, Apache or a research-only licence
on behalf of the authors and institution.

Relevant MIT guidance:

- <https://tlo.mit.edu/researchers-mit-community/protect/software-open-source-protection>
- <https://tlo.mit.edu/sites/default/files/2023-10/MITLL_Software_Copyright_Disclosure_Instructions_and_Form.pdf>

## Embedded third-party components

The application embeds Sparkle, py2Dmol, RDKit MinimalLib, 3Dmol.js and an
ipSAE-derived implementation. Their notices and exact available licence texts
are enumerated in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and copied
into every built application at `Contents/Resources/ThirdPartyLicenses`.

## Downloaded scientific engines

Model engines, Python packages, source repositories and checkpoints are not
included in the application download. The user chooses them in the Engines
screen, and Studio downloads them into `~/.iproteinstudio`. Each remains subject
to its upstream licence and any checkpoint or service-specific terms. A licence
for iProteinStudio cannot override those terms.

AlphaFold 3 parameters are neither downloaded nor redistributed by this project.

## Release checklist

Before a broadly advertised public beta:

1. complete the MIT software copyright disclosure;
2. confirm every author, sponsor and source of funding;
3. have MIT review the proposed source and binary distribution licence;
4. review the engine/checkpoint terms presented during optional installation;
5. replace the status-only `LICENSE` file only with the approved text; and
6. record the approval and exact licence version in the Lab Book.

This inventory is engineering documentation, not legal advice.
