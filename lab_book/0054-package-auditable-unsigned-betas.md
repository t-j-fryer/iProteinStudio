---
entry: 0054
title: Package auditable unsigned betas without weakening signed releases
date: 2026-09-01
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, macOS
tags: [release, security, privacy, licensing, sparkle, distribution]
---

# Package auditable unsigned betas without weakening signed releases

## Context

The application already had a local ad-hoc bundle builder and the notarised
Developer ID release route recorded in Entry 0044. It did not have an explicit
route for producing an unsigned beta that another Mac could install, nor a
complete set of user-facing privacy, support, security and licensing documents.
The signed release script correctly stopped at the missing Developer ID identity.

The original iProteinStudio source also does not yet have an institutionally
approved open-source licence. Because this work was developed in an MIT context,
the implementation must not invent ownership or silently grant a licence before
MIT Technology Licensing Office review.

## What changed

- Added `release/release_app.sh --unsigned-beta`, which creates versioned DMG and
  ZIP artifacts for Apple Silicon without changing the notarised release path.
- Required a clean tree by default. `--allow-dirty` exists only for explicit
  local testing and stamps the provenance as `dirty-local-test`.
- Added embedded distribution metadata that distinguishes development,
  unsigned-beta and Developer ID builds.
- Fixed the update service so an ad-hoc beta cannot enable Sparkle merely because
  the feed URL and public key are present. Only a signed-update build may start
  Sparkle; unsigned betas explain that updates are manual.
- Added SHA-256 checksums and a build-provenance record to each beta directory.
- Added a drag-to-Applications DMG with the install guide and privacy, security,
  support, licensing and third-party notice documents.
- Added top-level privacy, support, security and licensing documentation.
- Added exact licence texts for Sparkle, RDKit, 3Dmol.js, py2Dmol and IPSAE to
  the application bundle, with hashes for the vendored RDKit and 3Dmol assets.
- Preserved the existing Developer ID/notarisation/Sparkle release contract.
- Added a regression test for the unsigned-beta release boundary.

## Results

| Check | Result |
|---|---|
| Normal unsigned-beta command on a dirty tree | Correctly refused |
| Explicit local-test package | DMG and ZIP produced |
| Artifact sizes | DMG 11 MB; ZIP 9.7 MB |
| SHA-256 verification | 2/2 artifacts passed |
| DMG image verification and read-only mount | Passed |
| Packaged application architecture | `arm64` |
| Packaged signature | Valid ad-hoc signature |
| Embedded distribution channel | `unsigned-beta` |
| Sparkle signed-update flag | `false` |
| Embedded third-party licence files | 6/6 present |
| Unsigned release contract | Passed |
| Existing signed-update release contract | Passed |
| Iterative-results UI contract | Passed |
| `swift build` (debug) | Passed |
| Swift release build used by packaging | Passed |

The test artifacts were generated from source commit
`70a9875055f7439eb66fbe37a3303b8889a3b503` with uncommitted work and therefore
carry the source-state label `dirty-local-test`:

- DMG SHA-256:
  `75c2ea2e84e9845de4473bb7a4aa7fdc4f2dd17cd65050ca4210e0328c0be1a6`
- ZIP SHA-256:
  `b25b559d0145e7af860c5248a47f46a2a75e0c42c844e4b219884c19b54b4f4a`

## Decisions

An unsigned beta is a separate, deliberately inferior distribution channel: it
uses an ad-hoc signature, is not notarised, and cannot silently participate in
Sparkle updates. The signed release remains the intended public route once
Developer ID credentials are available.

No open-source licence was selected for original iProteinStudio code. The new
`LICENSE` and `LICENSING.md` files state the present status and direct the project
toward MIT disclosure and open-source review. This resolves ambiguity for a
controlled evaluation build without making an irreversible ownership claim.

## Reproduction

From a clean, committed source tree:

```bash
bash release/release_app.sh --unsigned-beta
```

For a local test artifact while intentionally retaining uncommitted work:

```bash
bash release/release_app.sh --unsigned-beta --allow-dirty
```

Contract and build checks:

```bash
bash Tests/test_unsigned_beta_release_contract.sh
bash Tests/test_update_release_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
swift build
```

## What was not tested

- The DMG has not yet been downloaded through a browser or opened on a second
  Mac, so quarantine/Gatekeeper presentation on a recipient machine remains to
  be validated.
- No Developer ID signature or Apple notarisation was performed because the
  required certificate is not available.
- This dirty-tree artifact is not a publishable release. A clean artifact must
  be rebuilt after the source changes are committed.
- The original vendored RDKit and 3Dmol.js imports did not retain upstream
  release tags, so their exact files are pinned by SHA-256 rather than a claimed
  tag. Future refreshes should record both.
- Downloaded engine licences and model terms remain the responsibility of their
  respective upstream projects and should receive release-by-release review.
- No public download website, branded app icon or automated hosting was added.

## Next actions

1. Test the DMG on a second Apple-Silicon Mac, including Gatekeeper and a small
   engine installation/run.
2. Commit the release work and rebuild from the clean tree before publishing.
3. Submit the software disclosure and proposed open-source release to MIT TLO.
4. Obtain Developer ID credentials before enabling the public signed channel.
