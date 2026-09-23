def run(config):
    from catboost import CatBoostClassifier, CatBoostRegressor

    train, test, fit, valid = tabular_data(config)
    categories = train[config["features"]].select_dtypes(exclude=np.number).columns.tolist()
    for frame in (train, test):
        for col in categories:
            frame[col] = frame[col].fillna("__MISSING__").astype(str)

    def factory(fitting, validation, phase):
        cls = CatBoostClassifier if config["problem"] == "classification" else CatBoostRegressor
        model = cls(
            iterations=config["iterations"],
            random_seed=config["seed"],
            thread_count=1,
            verbose=False,
            allow_writing_files=False,
            cat_features=categories,
        )
        return model.fit(fitting[config["features"]], fitting[config["target"]])

    tabular_finish(config, train, test, fit, valid, factory)
