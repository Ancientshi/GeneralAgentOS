---
name: tabular-modeling
description: Train and validate classification or regression models on tabular data with explicit features, leakage-aware splits and reproducible prediction artifacts.
---

Use `ds_list_recipes` and `ds_render_recipe`. Available families: `tabular-sklearn`,
`tabular-catboost`, `tabular-autogluon`, `tabular-tabpfn`. The last three require optional
dependencies; TabPFN also requires an operator-prepared local checkpoint. Check the model's
resource card for limits and weight terms before proposing its use.

Derive feature availability from prediction time. Explicitly select features, excluding target,
identifiers, future outcomes and proxies unavailable at inference. Use group splits for repeated
entities, chronological splits for temporal generalization, and random splits only for an
appropriate independent sampling design. Transformations are fit inside the training split.
The generic recipe supports one target; do not force multioutput tasks through it.

Start with a permitted simple model, then compare candidates using the same validation design.
The AutoGluon template uses bounded RF/XT models; it is not the full unrestricted AutoGluon preset.
TabPFN uses its own preprocessing; do not prepend the generic one-hot/scaling pipeline.

Recipes output class labels or regression point predictions. AUC, log-loss or competition
probability submissions require a probability adapter with an explicit positive class and column
order. Do not rename hard labels to imply probabilities. Preserve submission row IDs/order and
the task's exact output columns. Inspect the receipt; only the benchmark evaluator provides the
official score. If the task mandates an exact algorithm, implement that instruction directly.
