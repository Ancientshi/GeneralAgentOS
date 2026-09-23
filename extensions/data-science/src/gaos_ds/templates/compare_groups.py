def run(config):
    from scipy.stats import ttest_ind

    frame = read_csv(config["input_path"])
    series = frame[config["group_column"]].astype("string")
    a = pd.to_numeric(frame.loc[series == config["group_a"], config["value_column"]], errors="raise").dropna()
    b = pd.to_numeric(frame.loc[series == config["group_b"], config["value_column"]], errors="raise").dropna()
    if min(len(a), len(b)) < 2 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Each selected group needs at least two finite observations")
    if a.var() == 0 and b.var() == 0:
        raise ValueError("Both groups have zero variance; Welch inference is undefined")
    result = ttest_ind(a, b, equal_var=False)
    interval = result.confidence_interval(confidence_level=0.95)
    info = receipt(
        config,
        [config["input_path"]],
        {
            "method": "independent-groups Welch t-test",
            "n_a": len(a),
            "n_b": len(b),
            "mean_a_minus_b": float(a.mean() - b.mean()),
            "p_value": float(result.pvalue),
            "confidence_interval_95": [float(interval.low), float(interval.high)],
            "missing_values": "dropped within each selected group",
            "interpretation": "Association under independent-observation assumptions; not causal evidence. One comparison, no multiplicity correction.",
        },
    )
    write_json(config["output"], info)
    print(json.dumps(info["diagnostics"]))
