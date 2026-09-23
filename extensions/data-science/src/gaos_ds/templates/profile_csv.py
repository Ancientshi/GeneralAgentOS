def run(config):
    frame = read_csv(config["input_path"])
    columns = []
    for name in frame:
        series = frame[name]
        item = {
            "name": name,
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "unique_non_null": int(series.nunique()),
        }
        if pd.api.types.is_numeric_dtype(series):
            finite = series[np.isfinite(series)]
            item["non_finite_non_null"] = int((series.notna() & ~np.isfinite(series)).sum())
            item["min"] = float(finite.min()) if len(finite) else None
            item["median"] = float(finite.median()) if len(finite) else None
            item["max"] = float(finite.max()) if len(finite) else None
        columns.append(item)
    info = receipt(
        config,
        [config["input_path"]],
        {
            "rows": len(frame),
            "columns": columns,
            "duplicate_rows": int(frame.duplicated().sum()),
            "note": "Descriptive file audit only; missingness mechanisms and causal claims are not inferred.",
        },
    )
    write_json(config["output"], info)
    print(json.dumps(info["diagnostics"]))
