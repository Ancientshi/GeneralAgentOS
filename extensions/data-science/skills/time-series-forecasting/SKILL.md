---
name: time-series-forecasting
description: Forecast one or multiple time series with explicit horizon, frequency, seasonal baselines and chronological backtesting; optionally use StatsForecast or local Chronos weights.
---

Determine the time index, entity key, frequency, horizon and information available at forecast time.
Separate future-known covariates from observed-only variables. Define an explicit policy for
duplicates, gaps and missing targets; templates reject these rather than silently imputing them.

Use `forecast-seasonal` as an initial last-value or seasonal-naive baseline, then consider
`forecast-statsforecast` (AutoARIMA) or `forecast-chronos` (local Chronos-2). The templates accept
a history-only CSV and hold out the last horizon of each series. For model selection beyond a
quick check, use multiple rolling cutoffs with the same forecast horizon and explicit cutoffs.
Avoid shuffling rows for validation or using realized future targets as covariates.

Check dependency and weight availability through the rendered preflight and resource card.
Chronos-2 itself supports more settings; this template implements univariate prediction only.
The default benchmark runner is CPU-only. A CUDA parameter is useful only with a separately
configured GPU-capable executor; do not claim GPU availability from the model name.

Inspect timestamp alignment and per-series errors as well as aggregate error. Templates produce
`unique_id,ds,prediction`; adapt that table to the selected task's required ordering and schema.
Record frequency, season length, horizon, model snapshot hashes and internal validation separately
from the official benchmark feedback.
