---
name: benchmark-runner
description: Select and run a data-science benchmark task through the benchmark MCP tools, then retrieve its automatically routed evaluation and feedback. Use for Ambig-DS, DARE-Bench, DDR-Bench, CoDA-Bench or DAComp tests.
---

Use the benchmark MCP tools attached to this agent. If they are absent, explain that the
benchmark profile must be connected; do not invent tools or scores.

1. Resolve the requested benchmark and exact task ID with `list_benchmarks` and `list_tasks`.
   Respect the selected task; ask for the variant when there are several. Do not interpret
   a list position as an ID. Names are `ambig-ds`, `dare-bench`, `ddr-bench`, `coda-bench`, `dacomp`.
2. Read `get_task`, then call `start_run`. If blocked, report its readiness issues without
   substituting generated data, a different task or a different scoring rule.
3. Solve the task using `read_file`, `write_file` and `execute_python`. Python runs in
   `/workspace`; paths there persist between calls. Follow the actual task prompt and
   produce its required artifacts. Ambig-DS Target submissions use columns `id,prediction`;
   original competition column names are restored by the evaluator. Objective submissions
   use the competition's original submission columns. Do not retrieve
   reference solutions, hidden labels, rubrics or another run's results to solve a task.
4. Call `submit_run` once artifacts are ready. It freezes the attempt and selects the
   evaluator without requiring you to choose a metric. If required files are missing,
   the attempt stays open for correction. An accepted submission is final for this run.
5. Use `run_status` with `wait_seconds=30` until evaluation finishes. While it is pending,
   keep the user informed of the run ID and state; avoid rapid repeated polls. Report benchmark, task,
   variant, run ID, native metrics and feedback. Failed evaluation is not a zero score.

Each comparison should use a fresh conversation and a fresh run. Do not pool scores
across different benchmarks or variants: metric scales and directions differ. Any retry
after seeing test feedback is a new attempt and must be identified as such.

This skill is a harness, not a collection of solution hints. A single interactive run is
useful for debugging; official paper replication may require a separate blinded solver,
the upstream prompts, interaction policies, budgets and complete task coverage.
