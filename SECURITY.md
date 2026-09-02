# Security policy

## Supported builds

The newest published beta is the only supported beta. Trusted beta builds can
receive application security fixes through Sparkle; local development builds
cannot.

Unsigned beta builds are ad-hoc signed and are not notarized by Apple. macOS
therefore cannot establish the developer's identity or confirm an Apple malware
scan. Use only an artifact obtained from the official iProteinStudio release
location, verify its published SHA-256 checksum, and follow
[the unsigned installation guide](docs/INSTALL_UNSIGNED_BETA.md).

## Reporting a vulnerability

Do not open a public issue for a vulnerability or include unpublished biological
sequences, credentials, tokens or identifiable local paths in a report. Use
GitHub's private security-advisory route:

<https://github.com/t-j-fryer/iProteinStudio/security/advisories/new>

Include the iProteinStudio version/build, macOS version, Apple chip, affected
workflow, and a minimal reproduction with sensitive scientific data removed.

## Release integrity

- Every unsigned beta includes `SHA256SUMS.txt` for its DMG and ZIP.
- The DMG includes its source commit and whether it was built from a clean tree.
- Dirty-tree artifacts are labelled `dirty-local-test` and must not be published.
- Engine and checkpoint downloads use pinned sizes and/or SHA-256 checks and are
  independent of application updates.
- Trusted-beta update archives require a valid Sparkle EdDSA signature matching
  the public key embedded in the installed app. HTTPS protects feed transport.
- This update signature authenticates the project release key, not an Apple-
  verified developer identity. Future public releases should additionally use
  Developer ID, Hardened Runtime, notarization and stapling.

Never work around a checksum failure or use `xattr` to suppress quarantine for an
artifact whose origin and checksum have not been independently verified.
