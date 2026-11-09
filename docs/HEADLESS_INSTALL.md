# Install and use Studio without the app

Studio's CLI and MCP bridge run on native Apple-silicon macOS, including an SSH
session without a desktop. The installer needs neither sudo nor Homebrew, Git,
system Python, Xcode or Command Line Tools. A Git checkout is one way to obtain
the source; downloading and extracting GitHub's source archive also works.

## Install from GitHub

If Git is already available:

```bash
git clone https://github.com/t-j-fryer/iProteinStudio.git
cd iProteinStudio
bash install.sh --base
```

Without Git or a browser, download the source archive with macOS's built-in tools:

```bash
curl --fail --location --proto '=https' \
  https://github.com/t-j-fryer/iProteinStudio/archive/refs/heads/main.tar.gz \
  --output iProteinStudio-source.tar.gz
tar -xzf iProteinStudio-source.tar.gz
bash iProteinStudio-main/install.sh --base
```

Alternatively download **Code → Download ZIP** on GitHub, extract it, open a
terminal in that directory, and run `bash install.sh --base`. There is no Swift
build or app launch. For reproducible deployment, select a release tag or exact
commit instead of moving `main` and retain that source archive; its extracted
directory name changes accordingly. Do not update an active job's code.

`--base` selects the same base components as app Setup: RFD4, ESMFold2 Full,
Boltz2 and affinity, the MPNN family, AbMPNN and LASErMPNN. These are substantial
downloads. Select fewer engines if appropriate:

```bash
# Our remote prediction/design benchmark engines:
bash install.sh --with-boltz --with-rfd4 --with-esmfold2-full --with-esmfold2-600

# CLI/MCP and examples only, without any model weights:
bash install.sh --stage-only

# Read-only detection, including before installing anything:
bash install.sh --detect

# All Setup engine choices:
bash install.sh --setup-help
```

No arguments prints help and downloads nothing. Use `--all` only when all
supported engines are intended. Fast-600M is separate from the larger ESMFold2
Fast model. Model capabilities and macOS minimums remain those documented in
the [README](../README.md) and [runtime guide](PORTABLE_RUNTIME_IMPLEMENTATION.md).
Missing or incompatible engines fail explicitly rather than being replaced.

The default managed installation is `~/.iproteinstudio`. Override it using
`--root /path/without/whitespace` or `NANOHUNTER_ROOT`. Keep one installation and
execution queue for ordinary work on a physical Mac. An isolated qualification
root is useful for CPU installation tests; it must not become an independent
queue for overlapping GPU jobs.

## Use the CLI

```bash
"$HOME/.iproteinstudio/bin/studioctl" doctor
"$HOME/.iproteinstudio/bin/studioctl" detect
"$HOME/.iproteinstudio/bin/studioctl" project-create demo
"$HOME/.iproteinstudio/bin/studioctl" projects
"$HOME/.iproteinstudio/bin/studioctl" guide prediction
```

For a custom root, use its `bin/studioctl`. Launchers derive the managed root
from their own installation directory, so an unrelated shell's root setting
cannot redirect them. Add that `bin` directory to PATH if desired; the installer
does not edit shell startup files.

`doctor` checks that the bridge and request schemas load; it does not claim all
engines are installed. `detect` reports engine state. Project creation is
idempotent, validates the project name, and does not require an app preference
file. It never runs inference. Follow [CLI.md](CLI.md) for immutable workflow
planning, `start` with the returned plan ID/digest, monitoring and resume.

## Connect an assistant

The installed MCP command is:

```bash
"$HOME/.iproteinstudio/bin/studio-mcp" --profile read
# Separate registration for authorized submissions:
"$HOME/.iproteinstudio/bin/studio-mcp" --profile run
```

These use Studio's existing server and profiles. Admin remains disabled unless
explicitly enabled; ordinary workflow registration does not grant maintenance
access. Existing configuration automation is available at
`~/.iproteinstudio/mcp/configure.py`; see [AI assistants](AI_ASSISTANTS.md).

An assistant with authorized SSH access can invoke the remote CLI or transport
the stdio server over SSH without a PTY. Register remote read/run connections
separately from local ones and rediscover the deployed schemas. Keep protocol
stdout free of shell greetings. A hosted client that cannot initiate SSH needs
the separately authenticated HTTPS gateway described in the bridge guide.

A useful instruction to an assistant is:

> Read this repository's README and docs/HEADLESS_INSTALL.md. Install Studio's
> CLI/MCP and the engines I select into my managed root using install.sh. Start
> with detection; preserve existing projects and jobs. Run doctor and detect,
> then report the installation location and any failed or missing components.
> Do not start scientific jobs or install every optional engine unless requested.

## Update, retry and recover

Obtain the intended source version and repeat the same install command. The
bootstrap downloads a checksum-verified pinned Python toolchain when necessary,
stages the same pipeline, overlays, examples and MSA seeds as the app, and calls
the existing portable component installer. Weights remain separate upstream
downloads; they are not part of the source archive. Installed components and
verified assets are reused by the existing installer.

Staging takes the same execution lock as the app/broker and refuses an active
job or concurrent installer. It prepares resources before replacing live files;
a failed replacement rolls back, and a subsequent invocation recovers an
interrupted staging transaction. Existing projects, model assets, retained
runtimes, immutable job snapshots and generated/cached alignments are preserved.
Receipt: `receipts/headless-assets.json`, containing the asset inventory/digest.

Component installation keeps its existing partial-success behavior. A nonzero
exit or `NHDONE|partial` is a failed/incomplete installation, even when some
components succeeded. Retry the same selection; do not delete the installation
or choose weaker model settings to hide an installation failure. No success
message is printed by the wrapper after a failed component install.

After an update, reconnect long-running MCP clients. Existing scientific jobs
retain their original code and runtime; changed settings require a new plan.

## Install from an extracted app bundle

A release app's resources can bootstrap the same installation without opening
the app or moving it to Applications:

```bash
bash /path/to/iProteinStudio.app/Contents/Resources/iProteinStudioResources/pipeline/install_cli.sh --stage-only
```

Replace `--stage-only` with engine selections as needed. This is the same entry
point used by the checkout's root `install.sh`, not a second engine installer.
Use a source/bundle version that actually includes this headless entry point.
Local Beta app bundles retain their existing prohibition on shared-runtime
staging/maintenance; use the reviewed source route or public distribution bundle.

## Qualification limits

See [Lab0832](../lab_book/0832-qualify-headless-installation.md) for the precise
tests and actual clean-root installation results. Fixture tests and package
installation do not establish inference accuracy, every optional engine's fresh
installation, another Mac's compatibility, or Enverge-specific performance.
Remote deployment still needs the allocated host's inventory and bounded
workflow acceptance. No benchmark launches automatically during installation.
