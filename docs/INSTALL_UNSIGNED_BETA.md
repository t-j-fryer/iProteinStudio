# Install the unsigned iProteinStudio beta

This beta is built for Apple-silicon Macs running macOS 14 or later. It is
ad-hoc signed, not signed with an Apple Developer ID and not notarized by Apple.
The extra warning below is expected, but users should override it only for an
artifact obtained from the official iProteinStudio release location.

## Install

1. Download the Apple-silicon `.dmg` and its `SHA256SUMS.txt` file from the same
   iProteinStudio release.
2. Open the DMG and drag **iProteinStudio** onto the **Applications** shortcut.
3. Eject the DMG, then open iProteinStudio from Applications.
4. macOS will refuse the first launch because the developer cannot be verified.
   Open **System Settings → Privacy & Security**, scroll to **Security**, and
   click **Open Anyway** for iProteinStudio.
5. Confirm **Open** in the second macOS prompt. macOS remembers this exception
   for that copy of the app.

Apple documents this flow at:
<https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac>.
Managed institutional Macs may prohibit the override; contact the local IT
administrator rather than weakening device-wide security settings.

## Optional checksum verification

Checksum verification is not required to operate the app, but it confirms that
the downloaded file matches the release record. In Terminal, change into the
download folder and run:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

The DMG should report `OK`. Do not install it if the checksum differs.

## First launch

The app itself is small. Scientific engines and model checkpoints are separate,
often large downloads. The Engines screen states their purpose and approximate
disk use, and nothing is installed until the user confirms it. Projects, results
and engines are stored under `~/.iproteinstudio` rather than inside the app.

Remote MSA generation sends the submitted protein sequence to an external
alignment service. Review the `PRIVACY.md` included in the DMG before using
confidential sequences.

## Updates

Trusted unsigned betas can update the application through Sparkle. In
**iProteinStudio → Settings → Updates**, users may disable automatic checks or
automatic downloads and can always choose **Check for Updates…** manually.

Every executable update archive must carry a valid EdDSA signature from the
iProteinStudio release key embedded in this app. Sparkle rejects an archive that
does not match. This verifies that an update came from the same project release
key, but it does not make the app Developer ID signed or Apple notarized.

Application updates replace the interface and bundled pipeline code only. They
do not delete the managed runtime, workspaces, results, alignments or models, and
they never install large engines or checkpoints without separate confirmation.

Once a Developer ID-signed and notarized release exists, it will provide a normal
Gatekeeper launch while retaining the cryptographically verified Sparkle update
channel.
