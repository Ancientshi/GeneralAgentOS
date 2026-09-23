---
name: data-discovery-engineering
description: Locate relevant public task files, inspect tables and design validated joins or transformations for data analysis and data-engineering tasks.
---

Inventory the current task workspace with the connected file tool. Use filenames, schemas,
units and sample values to establish which tables can answer the question. `profile-csv` and
`sqlite-inspect` provide initial audits; the latter opens SQLite read-only and enumerates tables,
column definitions and row counts. It does not execute arbitrary SQL.

Use DuckDB for local multi-file SQL and Polars for lazy transformations where useful;
their resource cards provide official APIs, but they are catalog entries without dedicated
recipes in this release. Confirm they are installed in the executor before generating code.
Infer neither semantic equivalence nor join keys from similar column names alone.

Before a join, inspect key uniqueness, null keys and expected cardinality. After it, record
matched/unmatched counts, row expansion and aggregate checks. Preserve units, time zones and
provenance. Express task-derived constraints with assertions or Pandera; do not invent constraints
solely to make checks pass. DAComp DE tasks require their actual deliverable, not a substitute report.

Keep source inputs intact and write derived artifacts under distinct paths. Formal benchmark work
uses the files exposed by the task; online search cannot repair missing official benchmark data
by substituting an unrelated dataset. Report missing prerequisites via the benchmark tools.
