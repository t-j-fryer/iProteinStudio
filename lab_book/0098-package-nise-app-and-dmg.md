---
entry: 0098
title: Package the NISE app and DMG
date: 2026-09-05
author: gpt-6
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [nise, packaging, release]
---

## Context

The user requested an updated app and DMG after the ligand NISE integration
and Protein Hunter rename in [[0095-integrate-ligand-nise]]. The previous local
package was version 0.2.0 build 17.

## What was done

Incremented `BUILD_NUMBER` to 18 and used the existing unsigned-beta release
script with `--allow-dirty` to package the current working tree. Existing build
17 artifacts are retained. The app is assembled at `build/iProteinStudio.app`;
the DMG, ZIP, provenance, checksums and signed local appcast are placed under
`build/unsigned-beta-0.2.0-18/`.

## Results

No scientific performance measurements — packaging only.

| Check | Result |
|---|---|
| Production Swift build | Passed |
| Unsigned-beta and application-update contracts | Both passed |
| App resources and deep strict code signature | Passed for build output and mounted DMG copy |
| App metadata | 0.2.0 (18), arm64, unsigned-beta, MCP v9 |
| DMG integrity and read-only mount | Passed; detached after inspection |
| DMG app versus build output | All 376 entries match by file hash, mode and symlink target |
| DMG and ZIP SHA-256 manifests | Both passed |
| Sparkle local appcast | EdDSA-signed archive entry generated |

The initial recursive `diff` reported directory-loop warnings for Sparkle's
framework links. A second comparison explicitly preserved symlink targets and
hashed regular files without following links; every entry matched.

Build output is saved beside the artifacts as `BUILD_LOG.txt`. DMG SHA-256:
`5d10ef6bff39f42d0ed6f65b685b9899c190de44fc3eb6289703ed4677822981`.
ZIP SHA-256:
`8ab9bbd058e3592db9b1c79150d2a9b3f415edb610fb145d370dbeab66138b8f`.

## Decision and rationale

Retained version 0.2.0 and incremented its build number, following the existing
local beta process. The working tree contains uncommitted integration work,
so the artifacts explicitly record `dirty-local-test` provenance. A public
release would require a reviewed clean source state; no publishing was requested.

## Reproduce

```bash
release/release_app.sh --unsigned-beta --allow-dirty
bash Tests/test_unsigned_beta_release_contract.sh
bash Tests/test_update_release_contract.sh
bash Tests/test_packaged_resource_bundle.sh build/iProteinStudio.app
hdiutil verify build/unsigned-beta-0.2.0-18/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg
(cd build/unsigned-beta-0.2.0-18 && shasum -a 256 -c SHA256SUMS.txt)
```

The release command requires access to macOS disk-image utilities, Swift build
caches and the existing project Sparkle signing key in the login Keychain.

## Limits and what was not tested

This is an ad-hoc-signed local beta, without Developer ID signing or Apple
notarization. No public feed or GitHub release is updated. No new scientific
campaign, throughput measurement, second-Mac installation or Sparkle update
installation is part of this packaging pass. GUI interaction was not tested.
Neither `/Applications/iProteinStudio.app` nor the user's Applications copy
exists; the repository's app bundle is the app being updated.

## Next

Open build 18 to use the NISE tab and Protein Hunter branding. Cross-Mac and
public-distribution acceptance remain separate release work.
