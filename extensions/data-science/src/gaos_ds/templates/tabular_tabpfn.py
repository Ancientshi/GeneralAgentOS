def run(config):
    import os

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TABPFN_NO_BROWSER"] = "1"
    os.environ["TABPFN_DISABLE_TELEMETRY"] = "1"
    from tabpfn import TabPFNClassifier, TabPFNRegressor

    # Operator-provided local file; never auto-download the current default checkpoint.
    checkpoint = Path(config["model_path"])
    if not checkpoint.is_file():
        raise ValueError("Prepare the chosen TabPFN checkpoint in the sandbox image first")

    def factory(fitting, validation, phase):
        cls = TabPFNClassifier if config["problem"] == "classification" else TabPFNRegressor
        return cls(model_path=str(checkpoint), device=config["device"], random_state=config["seed"]).fit(
            fitting[config["features"]], fitting[config["target"]]
        )

    tabular_finish(config, *tabular_data(config), factory)
