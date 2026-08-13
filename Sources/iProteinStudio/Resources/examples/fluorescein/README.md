# Fluorescein hydroxyethylamide

The worked small-molecule example. A fluorescein core with a short
hydroxyethylamide linker — which is what makes it a good teaching case rather
than just a dye.

The linker is the interesting part. Bury it and you get a binder you cannot
attach to anything; its flexibility is also irrelevant to how the pocket should
be shaped, so leaving it in confuses the conformer analysis. Click the atom where
it leaves the molecule and the app separates the recognition core from the
presentation region, then conditions RFdiffusion3 to bury the core and keep the
linker exposed.

Validated conditioning from the reference campaign: 31 heavy atoms, of which
**25 buried and 6 exposed** (the linker: `O17, C24, N44, C46, C45, O21` — note
those names shift when Boltz's affinity head is enabled, because it standardises
the SMILES first).

Net charge −2. Two plausible tautomers, which the chemistry check will tell you
about.
