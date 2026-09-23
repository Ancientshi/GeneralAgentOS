def run(config):
    import os

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from chronos import Chronos2Pipeline

    path = Path(config["model_path"])
    if not path.is_dir() or not (path / "config.json").is_file():
        raise ValueError("Prepare a complete local Chronos-2 snapshot in the sandbox image")
    pipeline = Chronos2Pipeline.from_pretrained(str(path), device_map=config["device"], local_files_only=True)

    def forecast(frame, horizon):
        result = pipeline.predict_df(
            frame, prediction_length=horizon, id_column="unique_id", timestamp_column="ds", target="y"
        )
        return result.rename(columns={"predictions": "prediction"})[["unique_id", "ds", "prediction"]]

    forecast_finish(config, forecast_data(config), forecast)
