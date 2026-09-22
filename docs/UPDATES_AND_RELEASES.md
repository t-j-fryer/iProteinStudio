# Application updates and GitHub Releases

## How an update reaches a user

1. The user installs a **distribution** DMG from an app release on
   [GitHub](https://github.com/t-j-fryer/iProteinStudio/releases), then runs the
   copy in Applications.
2. Sparkle checks the HTTPS [appcast](https://raw.githubusercontent.com/t-j-fryer/iProteinStudio/main/appcast.xml).
   It compares the feed's build number with the installed `CFBundleVersion`.
3. An eligible newer entry points to an app ZIP on its GitHub Release. Sparkle
   presents release notes and handles downloading/installing according to the
   user's preferences.
4. Sparkle verifies the ZIP's EdDSA signature with the public key embedded in the
   installed app before extraction. It replaces that app copy and relaunches it.

**A Git push alone does not update anyone's app.** A release needs the built
archive, its signature and a published appcast entry. GitHub's prerelease label
does not control Sparkle eligibility; the appcast does.

The menu **iProteinStudio → Check for Updates…** checks immediately. **Settings →
Updates** controls automatic checks and downloads. Studio leaves Sparkle's
permission defaults intact: if the user has not made a choice, Sparkle normally
asks about automatic checks on the second app launch. Declining keeps manual
checking available. These are scheduled checks while the app is running, not a
push notification whenever code changes. See Sparkle's
[permission behavior](https://sparkle-project.org/documentation/custom-user-interfaces/)
and [publishing contract](https://sparkle-project.org/documentation/publishing/).

Local development builds (`swift run` or ordinary `build_app.sh`) deliberately
have updates disabled. Older builds without an updater need one manual install
of a distribution DMG. Multiple installed app copies update independently;
**Settings → Updates → Find other copies** helps identify them.

## What GitHub hosts

| Asset | Purpose | How it reaches users |
| --- | --- | --- |
| `vVERSION-beta` app release | DMG for installation, signed ZIP for Sparkle, checksums and build provenance | Manual first install; subsequent appcast-driven updates |
| `appcast.xml` on `main` | Version/build, compatibility, release notes, archive URL/signature | HTTPS checks by Sparkle |
| `runtimes-…` release | Immutable optional Python/engine runtime archives | Selected through **Engines**, using the catalog bundled in the app |
| Repository source | Development, documentation and reproducibility | Cloning source does not install an app update |

Learned model weights are not redistributed in these runtime archives. They are
separate, checksum-verified downloads from approved upstream providers.

App updates deliver UI, adapters, schemas and the trusted runtime catalog.
Updating that catalog can offer a new engine/profile in **Engines**, but does not
silently download or activate it. Existing job plans retain their recorded code,
portable runtime identities and model assets. See [runtime preservation](PORTABLE_RUNTIME_IMPLEMENTATION.md).

## Current distribution status

GitHub hosts the trusted-beta releases now. They are ad-hoc signed and their
update archives use the project's Sparkle EdDSA key. They are **not** Apple
Developer ID signed or notarized. Sparkle signatures verify continuity with the
project's key; they do not replace Apple's identity/notarization checks or the
first-install Gatekeeper approval.

The empty-root installer test, paired runtime tests, app checksums and update
signatures have been checked on the development Mac. A full old-app-to-new-app
installation on a fresh second Mac is still a separate acceptance test. See
[Lab Book 0177](../lab_book/0177-integrate-psichic-portable-runtimes.md) and
[licensing status](../LICENSING.md).

## Maintainer release procedure

1. Update `VERSION`, increase `BUILD_NUMBER`, and add concise release notes to
   `CHANGELOG.md`. Increase `pipeline/mcp/MCP_VERSION` when the staged bridge
   changes. Keep the app's bundle identifier and Sparkle public key stable.
2. Run the relevant [tests](TESTING.md) and `swift build`. Commit a clean release
   checkout. Never include model weights or unrelated local experiments.
3. Publish the current trusted-beta channel:

   ```bash
   bash release/release_app.sh --publish-unsigned-beta
   ```

   The command builds and checks the bundle, creates a DMG and ZIP, signs the
   ZIP, generates the appcast, publishes `vVERSION-beta` with its assets, then
   commits/pushes the generated feed to `main`. Existing published versions must
   not be overwritten: increment the version/build for a correction.
4. Verify the GitHub asset sizes/digests, the live appcast URL, its build number
   and ZIP signature. Confirm a previous distribution bundle uses the same feed
   and public key. Record what was tested, including whether an actual updater
   installation on another Mac was performed.

For a local package without publication, use `--unsigned-beta`. The
`--allow-dirty` option creates a clearly marked local-only test artifact and
must not be used for publication. Release signing uses the private key in the
maintainer's login Keychain (`iproteinstudio`); only its public half belongs in
`release/sparkle_public_key.txt`. Keep an encrypted offline backup of the private
key. CI runs fixture tests; it does not possess release credentials or publish
app builds automatically.

### Engine releases

Build a distinct portable runtime identity, qualify relocation and scientific
outputs, publish its archive once, and update the bundled trusted catalog with
its hashes and platform minimum. Ship the catalog through an app release.
Never overwrite a runtime archive or remove a version retained by a job. See
[extending the runtime system](PORTABLE_RUNTIME_IMPLEMENTATION.md#extending-the-system).

### Future Developer ID channel

The existing signed release path requires an installed Developer ID Application
identity and a `notarytool` Keychain profile, selected through
`IPROTEINSTUDIO_SIGNING_IDENTITY` and `IPROTEINSTUDIO_NOTARY_PROFILE`.
`--preflight`, `--build` and `--publish` provide that route. It adds Hardened
Runtime, notarization and stapling. Apple credentials and the separate
[institutional licensing review](../LICENSING.md) remain outstanding; do not
label a trusted beta as notarized or change licence terms as part of packaging.
