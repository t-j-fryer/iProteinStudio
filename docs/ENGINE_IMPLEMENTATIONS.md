# Installed workflow implementations

Studio's model/runtime revision identifies the upstream dependency. It does not
identify Studio's adapter code. New 0.2.42/build95 jobs additionally retain
`WORKFLOW_RELEASE.json` with the three optimized adapter checksums and a workflow
release generation. App snapshots record this identity in `snapshot.json`;
CLI/MCP preflight plans include it in `code_snapshot.workflow_release`.

The release contains Claude's qualified ESMFold2 folding-trunk BF16 change and
RFD4 tiled gate/layout transpose, fused triangle output gate, redundant transition
mask removal and in-place ReLU. These run through the existing shared adapters
in prediction, native generation and supported iterative/beam workflows. RFD4's
existing optimized-kernel switch still controls its fast path.

ESMFold2 defaults to BF16 trunk weights for Full, Fast and Fast-600M. Every new
prediction confidence file records `trunk_weight_dtype` and `trunk_modules`.
`IPROTEINSTUDIO_ESMFOLD2_TRUNK_DTYPE=float32` retains the explicit legacy precision
route; invalid values fail. BF16 is numerically close rather than bit-identical
to FP32; small confidence changes can affect a borderline hit cutoff. RFD4's
adopted operations passed exact-output comparisons. No universal campaign speedup
or cross-hardware accuracy equivalence is asserted.

To check the deployed code without opening the app:

```bash
"$HOME/.iproteinstudio/bin/studioctl" doctor
"$HOME/.iproteinstudio/bin/studioctl" detect
```

`doctor` reports both the executable bridge's `workflow_release` and the shared
`installed_workflow_release`; MCP `system_detect` reports the latter. A verified
release includes `generation`, `release`, defaults and actual adapter SHA-256s.
Missing metadata means historical/unversioned code, not a claim that optimizations
are present. A checksum mismatch fails rather than declaring that installation
current. After an update, reconnect long-lived MCP clients so they load bridge59.

Updated apps and headless installers refuse to stage an older generation or
conflicting contents under the same generation. Replacing an older app is still
essential: binaries released before this guard do not contain it. Local Beta does
not stage shared assets; install the matching public release or use its headless
installer for CLI/MCP. Each new Beta job snapshots its own bundle.

An existing accepted plan/job keeps its frozen scripts, runtimes and completed
outputs. Updating Studio does not retrofit its predictions with these changes.
Create a new plan/campaign to use the new code. Do not overwrite old snapshots or
mix old/new timing records when comparing performance.

For future adapter changes, increment the workflow release generation, update
its checksums, run the contracts and build/package checks, then verify installed
copies and a newly captured snapshot. Source commits alone do not deploy code.
