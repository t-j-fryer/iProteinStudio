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

### Interrupted downloads and partial setup

Build 34 and later continue installing independent components when one component
fails. The completion card names unfinished components and offers **Retry
unfinished components** and **Show setup log**. Verified files stay on disk;
interrupted transfers resume. A failed checksum is discarded. A retry repeats only
unfinished components from the reviewed selection, not successful engines.

Core ProteinMPNN, SolubleMPNN and LigandMPNN install independently of AbMPNN.
AbMPNN is selected by default, but can be deselected or retried separately in
**Engines**. If Zenodo is unavailable, Studio automatically tries the approved,
revision-pinned Mosaic copy. Its serialization differs, so Studio checks its own
pinned SHA-256; all tensors and checkpoint metadata were checked for exact equality
with the original (Lab Book 0123). Each installation records which source and
checksum it used. TLS and checksum verification are never disabled.

Boltz affinity, IntelliFold full v2, and Protenix v2/Mini checkpoint downloads are
also isolated from their shared runtimes. A failed extra does not invalidate its
completed base runtime. Requested engines with missing dependencies remain
unavailable; Studio never silently substitutes another model. A completed predictor
can still be used in **Predict** if core sequence-design setup failed. After
reopening Studio, **Engines** detects missing components and lets you install them.

Failures of prerequisites needed by all components, such as missing Apple build
tools or the shared managed-Python bootstrap, still need repair before setup can
proceed. If no approved download source is reachable, retry after connectivity
recovers; the app cannot manufacture missing model files.

Mosaic's source attribution and CC-BY-4.0 notice:
<https://github.com/escalante-bio/mosaic/blob/70fec525423f5f87156a1a957b4a4048f9f8e676/src/mosaic/proteinmpnn/NOTICE>.
Studio distributes installer code and checksums, not model weights.

### Apple tools needed before setup

Some engine dependencies compile native code, so setup needs Apple's **Command
Line Tools for Xcode**. The full Xcode application is not required.

Build 33 and later check the tools before downloading engines. If they are absent
or the compiler fails its check, Setup and Engines show these actions:

1. **Install Apple Tools** opens Apple's installation window directly. Complete
   that window, including Apple's license/authorization prompts.
2. If macOS reports that the tools are already installed, choose **Open Software
   Update** and install the applicable update. You can also open **System Settings
   → General → Software Update** yourself.
3. After Apple finishes, return to Studio and choose **Retry Setup**. The reviewed
   engine selection is retained, and the compiler is checked again before any
   engine downloads. Opening Apple's installer alone does not complete setup.

Terminal is not needed for this flow. Older app builds that only show the Terminal
instruction need an updated app to offer these buttons. Apple documents its tools
installer in [Installing the command-line tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools).
If retry still fails, use **Show log** to inspect the error; SDK selection or other
compiler problems may require additional diagnosis.

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
