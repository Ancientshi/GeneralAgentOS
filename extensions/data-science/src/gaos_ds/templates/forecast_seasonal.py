def run(config):
    def forecast(frame, horizon):
        result = []
        for key, group in frame.groupby("unique_id", sort=False):
            times = pd.date_range(group.ds.iloc[-1], periods=horizon + 1, freq=config["frequency"])[1:]
            last_season = group.y.to_numpy()[-config["season_length"] :]
            values = np.resize(last_season, horizon)
            result.extend(
                {"unique_id": key, "ds": time, "prediction": float(value)}
                for time, value in zip(times, values)
            )
        return pd.DataFrame(result)

    forecast_finish(config, forecast_data(config), forecast)
