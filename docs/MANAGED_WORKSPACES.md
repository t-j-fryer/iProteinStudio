# Saved runs from the app, CLI and MCP

The app discovers managed workspaces containing saved run markers, including
ones created through `studioctl project-create` or MCP. They appear in the
sidebar and All Runs after startup or the shared job refresh. Existing names,
forms and IDs are preserved. Archived workspaces are not restored automatically.

Discovery reads shallow directory/run metadata. It does not move results, modify
scientific outputs, create replacement jobs or rewrite preferences just to index
existing work. CLI-only workspaces use the same stable UUID as the bridge.

For the recent PD-L1 benchmark, the first25native families belong to
`figure3b-optimized-mac-0837`; the additional25native,50-family iterative and
50-family beam runs belong to `figure3b-optimized-mac50-0844`. Those are four
production run records, plus separately saved qualification runs. The matched25
CSV export is a derived subset of the completed50-family results, so it is not
another executed run. No rerun or scientific-output import is required.

Lab0857 records the discovery fix, metadata verification and UI qualification.
