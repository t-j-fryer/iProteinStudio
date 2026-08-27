# iProteinStudio release notes

## 0.2.0 — updater foundation

- Adds signed in-app update support and a visible **Check for Updates…** command.
- Adds update preferences for automatic checks and automatic app downloads.
- Keeps application updates separate from scientific engines and checkpoints.
- Adds a final, size-aware confirmation before any selected engine is installed.
- Preserves projects, results, alignments, environments and model weights when the app is updated.

This release does **not** download a model or checkpoint as part of the app
update. New scientific components remain explicit choices in **Engines**.
