---
entry: NNNN
title: <short imperative title>
date: YYYY-MM-DD
author: <human name, or model id e.g. claude-opus-5>
type: decision | experiment | benchmark | implementation | bugfix | port | audit
status: complete | in-progress | blocked | superseded
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, predictors, ui, install, performance]
---

## Context

Why this work happened. What was true before it. Link the entry or issue it follows on
from, e.g. `[[0002-inherited-speed-lessons]]`.

## What was done

Concrete actions and the files they touched. Enough that someone can find the code.

## Results

Numbers, with units and replicate counts. State the machine if it differs from the
header. If nothing was measured, write `no measurements — implementation only` rather
than implying performance was verified.

| Condition | n | Metric | Value |
|---|---:|---|---:|

## Decision and rationale

What we chose, what we chose against, and why. **The alternatives matter** — an entry
that records only the winner cannot stop someone re-litigating it.

## Reproduce

Exact commands, with absolute paths where they matter.

```bash
```

## Limits and what was not tested

Be specific. Which lengths, topologies, ligand sizes, predictors, and hardware are
outside what was measured. What would falsify the conclusion.

## Next

Open questions and the obvious next step for whoever inherits this.
