---
entry: 0055
title: Enable cryptographically verified Sparkle updates for trusted betas
date: 2026-09-01
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, macOS
tags: [release, sparkle, security, updates, distribution]
---

# Enable cryptographically verified Sparkle updates for trusted betas

## Question

Can a small group of mutually trusting testers receive in-app updates before a
Developer ID certificate is available, without accepting arbitrary executable
archives from the update host?

## Finding

Yes, for regular application-bundle updates. Sparkle separates its EdDSA archive
signature from Apple's Developer ID code signature. An ad-hoc-signed application
still lacks Apple identity verification and notarization, but Sparkle can require
that every replacement ZIP match the project public key embedded in the app.

This is intentionally a controlled beta trust model, not a substitute for the
Developer ID and notarization route planned for public distribution.

## Implementation

- Trusted-beta bundles now enable `SPUStandardUpdaterController` only when their
  HTTPS feed, embedded public key and explicit Sparkle-update build marker are
  all present.
- Local development builds still disable the updater.
- Settings identify the beta trust boundary: archive signatures are verified,
  while Apple has not verified or notarized the developer.
- `release/release_app.sh --unsigned-beta` now fails closed unless the private
  Keychain key matches `release/sparkle_public_key.txt`.
- Every beta build generates an appcast entry containing a Sparkle EdDSA
  signature over the exact update ZIP.
- `--publish-unsigned-beta` provides one clean-tree operation that creates a
  GitHub prerelease, uploads the ZIP, DMG, checksums and provenance, and commits
  the generated appcast to `main`.
- Engine and checkpoint installation remains outside Sparkle and continues to
  require separate size-aware confirmation.
- Privacy, security, installation, release and README documentation now explain
  the distinction between project-key verification and Apple notarization.

## Verification

| Check | Result |
|---|---|
| `swift build` | Passed |
| Release Swift build | Passed |
| Unsigned-beta release contract | Passed |
| Existing signed-release contract | Passed |
| Iterative-results UI contract | Passed |
| Ad-hoc nested code-signature verification | Passed |
| Sparkle appcast entry generated | Passed |
| ZIP signature independently verified with `sign_update --verify` | Passed |
| Appcast download URL points to `v0.2.0-beta` ZIP | Passed |
| DMG checksum and image verification | Passed |
| Read-only DMG mount and content inspection | Passed |
| Packaged `IPStudioSparkleUpdateBuild` | `true` |

The replacement private-test artifact remains a deliberately non-publishable
`dirty-local-test` build. Its checksums are:

- DMG: `e269cfb1536ebc3df385c01416dba5e761862eb98b9154ac567f9ffef3b0332e`
- ZIP: `4f1972eec7e2fccedbe0cce9a70f5aa607a6a5904ee78bfc4bec8505847982c4`

## What was not tested

- No beta was published and the repository's current public appcast remains an
  empty feed. This local artifact is updater-ready but has no newer published
  version to discover yet.
- A genuine beta-to-beta installation through Sparkle was not run. That requires
  two increasing build numbers, hosted release assets and the second test Mac.
- Browser quarantine and the initial **Open Anyway** flow remain untested on the
  second Mac.
- Apple Developer ID verification, Hardened Runtime, notarization and stapling
  remain untested and unavailable.

## Acceptance test

1. Install this `0.2.0 (2)` test DMG on the second Mac and confirm the trust note
   and enabled update controls in **Settings → Updates**.
2. After committing the source, increment `BUILD_NUMBER`, build and publish the
   next clean trusted beta with `--publish-unsigned-beta`.
3. On the second Mac choose **Check for Updates…**, inspect the release notes,
   install and relaunch.
4. Confirm the new build number, intact projects/runtime and absence of any
   engine or checkpoint download.
5. Record the full acceptance result in a new Lab Book entry.
