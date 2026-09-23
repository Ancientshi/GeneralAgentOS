def run(config):
    from statsforecast import StatsForecast
    from statsforecast.models import AutoARIMA

    def forecast(frame, horizon):
        model = StatsForecast(
            models=[AutoARIMA(season_length=config["season_length"])], freq=config["frequency"], n_jobs=1
        )
        result = model.forecast(df=frame, h=horizon)
        return result.rename(columns={"AutoARIMA": "prediction"})[["unique_id", "ds", "prediction"]]

    forecast_finish(config, forecast_data(config), forecast)
