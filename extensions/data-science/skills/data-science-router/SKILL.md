---
name: data-science-router
description: Choose data-science models, methods and executable recipes for a dataset or benchmark task using the connected resource catalog. Use when selecting analysis capabilities, comparing modeling approaches or finding reusable data-science tools.
---

Use `ds_recommend` with an explicit capability and `ds_get_resource` for the selected resource.
Its benchmark mapping is an integration suggestion, not evidence of author usage or superior scores.
Inspect `ds_list_recipes` for current parameters, dependencies and validation status.

Route to `tabular-modeling`, `time-series-forecasting`, `evidence-based-analysis`,
`data-discovery-engineering` or `resource-research` according to the task.
Resolve target, unit of analysis, prediction horizon, metric and permitted inputs from the public
request. If ambiguity changes the result, ask only for that missing decision. Do not consult private
benchmark metadata to guess the intended answer.

For benchmark work, use `benchmark-runner` to select/start the task. DARE instruction-following
tasks may mandate a particular estimator, split and preprocessing; that instruction overrides
generic recipes. Use richer model selection only when permitted by the selected task.

`ds_render_recipe` returns code; it does not execute it. Pass its `preflight_code` to
`execute_python(run_id, code=...)`, check dependencies, then pass its `code` to the same executor.
Save the code and its SHA-256 in the run workspace with `write_file`. Recipes produce receipts;
inspect them before adapting outputs to the task's required artifact schema. If dependencies are
missing, report the package/image requirement or choose an allowed installed method.
Use a configured sandbox for other agents; this service does not provide a host Python executor.

Treat local validation as diagnostic. Submit through the benchmark tools for official evaluation.
Record retries after evaluator feedback as separate attempts. For fair comparisons, fix the catalog,
recipe hashes, model checkpoints, data, budgets and external-resource policy across agents.
