def run(config):
    from sklearn.compose import ColumnTransformer, make_column_selector
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    def factory(fitting, validation, phase):
        numeric = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                ("scale", StandardScaler()),
            ]
        )
        category = Pipeline(
            [
                ("impute", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                ("encode", OneHotEncoder(handle_unknown="ignore")),
            ]
        )
        transform = ColumnTransformer(
            [
                ("numeric", numeric, make_column_selector(dtype_include=np.number)),
                ("category", category, make_column_selector(dtype_exclude=np.number)),
            ]
        )
        classifier = config["problem"] == "classification"
        if config["model"] == "linear":
            estimator = (
                LogisticRegression(max_iter=1000, random_state=config["seed"]) if classifier else Ridge()
            )
        else:
            cls = RandomForestClassifier if classifier else RandomForestRegressor
            estimator = cls(n_estimators=100, random_state=config["seed"], n_jobs=1)
        return Pipeline([("preprocess", transform), ("model", estimator)]).fit(
            fitting[config["features"]], fitting[config["target"]]
        )

    tabular_finish(config, *tabular_data(config), factory)
