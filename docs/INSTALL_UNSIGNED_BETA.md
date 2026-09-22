# Install the iProteinStudio trusted beta

Get the Apple-silicon `.dmg` from the newest **app** release on
[GitHub Releases](https://github.com/t-j-fryer/iProteinStudio/releases).
App tags look like `v0.2.3-beta`. The separate `runtimes-…` release is an engine
package store used automatically by Studio, not an alternative app download.

These builds are ad-hoc signed and Sparkle updates are cryptographically signed,
but Apple has not Developer ID signed or notarized the app. The first launch can
therefore require Apple's per-app approval. See [licensing status](../LICENSING.md).

## Requirements

The app needs Apple Silicon and macOS 14 or later. Current Protenix v2/Mini
packages need macOS 26.0 or later; OpenFold3/RFdiffusion3 need 26.2 or later.
These are minimums. **Engines** disables selections incompatible with the Mac.

Portable engine installation requires internet access and sufficient disk space,
not Xcode, Command Line Tools, Git, Homebrew or your own Python. Developer
source-build instructions are separate in [CLI](CLI.md#apple-compiler-setup-errors).
Fresh-Mac acceptance remains outstanding; see [qualification limits](PORTABLE_RUNTIME_IMPLEMENTATION.md#qualification-and-limits).

## Install

1. Download the app DMG. Each release also provides `SHA256SUMS.txt` and
   `BUILD_PROVENANCE.txt` for verification.
2. Open the DMG and drag **iProteinStudio** to **Applications**.
3. Eject the DMG and launch the copy in Applications.
4. If macOS blocks the launch, open **System Settings → Privacy & Security** and
   choose **Open Anyway** for this app, then confirm **Open**.
5. In Studio, choose the engines needed for your work and review their download
   and disk-space requirements before installing.

Use the override only for the official release. Managed institutional Macs can
restrict it; consult your IT administrator. Apple's
[opening an app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac)
describes the system flow.

## Engines and interrupted setup

The app download contains the interface and pipeline code. Engine runtimes and
model weights are separate downloads. Their verified files, receipts, projects
and results remain under `~/.iproteinstudio`, outside the app bundle.

Setup reports unfinished components and offers **Retry unfinished components**
and **Show setup log**. Completed independent components remain available.
Interrupted transfers retain resumable partial files; checksum failures never
activate an unchecked runtime. Requested engines with missing prerequisites stay
unavailable rather than silently using another model.

NESSO and PSICHIC install their required ESM assets with their selected component.
Optional checkpoints such as Boltz affinity and IntelliFold full remain separately
selectable. No manual runtime archive extraction is needed.

## Updates

Choose **iProteinStudio → Check for Updates…** to check immediately. Under
**Settings → Updates**, control automatic checking and automatic app downloads.
With default settings, Sparkle asks permission for automatic checks on the
second launch. If declined, manual checking still works.

Sparkle downloads the signed ZIP from the corresponding GitHub Release and
verifies it against the public key embedded in Studio. It updates the running
app copy; keep one current copy in Applications. A development build made with
`swift run` or ordinary `build_app.sh` does not enable this distribution channel.
Older builds without the updater need one manual app installation.

App updates preserve projects, results and installed engines. New or changed
engine packages require separate confirmation in **Engines**. See
[Application and engine updates](UPDATES_AND_RELEASES.md).

## Optional checksum verification

In Terminal, calculate the downloaded DMG's SHA-256 and compare it with its entry
in `SHA256SUMS.txt`. The manifest also lists the ZIP; checking the entire manifest
requires both downloaded files. Do not install an artifact whose digest differs.

Remote MSA requests disclose the submitted sequences to the selected alignment
service. Review [Privacy](../PRIVACY.md) before using confidential inputs.
