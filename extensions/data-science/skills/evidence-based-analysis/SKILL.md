---
name: evidence-based-analysis
description: Explore datasets, test statistical questions and write evidence-backed findings with traceable calculations. Use for open-ended analysis, hypothesis comparisons, uncertainty and insight reports.
---

Start with the requested decision and unit of observation. Use `profile-csv` to inspect types,
missingness, duplicates and ranges; connect relevant files through `data-discovery-engineering`.
Maintain a claim ledger: claim, source file/table, filter, denominator, calculation and result.
For DDR-Bench and DAComp, build findings from accessible data; do not seek hidden questions,
rubrics or reference reports. A task may need several complementary analyses, not one model.

Use `compare-groups` for one independent two-group numeric comparison: it reports sample sizes,
mean difference, Welch p-value and interval. It does not support paired/repeated/clustered designs,
multiple-testing correction or covariate adjustment. Use an appropriate statsmodels/SciPy method
when those are needed, and state the design. Do not silently discard unanticipated groups.

Separate descriptive findings, predictions, associations and causal interpretations. SHAP
explains model outputs; it does not establish causation. Use DoWhy only with defensible treatment,
outcome, identification assumptions and a supplied/domain-supported graph.

Reports should connect a few consequential findings to reproducible tables/calculations and
uncertainty. Check subgroup sizes, missing-data exclusions, sensitivity to reasonable assumptions
and multiple comparisons where applicable. Do not substitute polished prose for executed evidence.
Use the task's required artifact names and official evaluator through benchmark-runner.
