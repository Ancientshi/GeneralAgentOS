def run(config):
    from autogluon.tabular import TabularPredictor

    def factory(fitting, validation, phase):
        label = config["target"]
        cols = config["features"] + [label]
        # Do not silently pick a foundation-model preset that downloads weights.
        model = TabularPredictor(
            label=label,
            eval_metric=config["metric"],
            problem_type=(
                "regression"
                if config["problem"] == "regression"
                else "binary"
                if fitting[label].nunique() == 2
                else "multiclass"
            ),
            path=str(local_path(config["model_dir"]) / phase),
            verbosity=1,
        )
        # AutoGluon selects its internal validation from fitting only. The outer holdout stays unseen.
        return model.fit(
            train_data=fitting[cols],
            time_limit=config["time_limit"],
            hyperparameters={"RF": {}, "XT": {}},
            num_bag_folds=0,
            num_stack_levels=0,
        )

    tabular_finish(config, *tabular_data(config), factory)
