"""Unexecuted fixed-family monthly learner; no market access on import/call."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
from method import ARMS, INTERACTIONS, STATE, STOCK, monthly_folds


def impute_training(train, test, *, state_arm):
    """Only state/interaction missingness is added; base rows are common finite."""
    if (
        not np.isfinite(train[:, : len(STOCK)]).all()
        or not np.isfinite(test[:, : len(STOCK)]).all()
    ):
        raise ValueError("Common stock-feature eligibility violated")
    missing_train, missing_test = ~np.isfinite(train), ~np.isfinite(test)
    medians = np.asarray(
        [
            np.median(train[np.isfinite(train[:, c]), c]) if np.isfinite(train[:, c]).any() else 0.0
            for c in range(train.shape[1])
        ]
    )
    x = np.where(missing_train, medians, train)
    y = np.where(missing_test, medians, test)
    if state_arm:
        x = np.c_[x, missing_train[:, len(STOCK) :].astype(float)]
        y = np.c_[y, missing_test[:, len(STOCK) :].astype(float)]
    return x, y, medians


def forecast(prepared, plan, *, record_fit, save_model):
    """Caller must pass actual priority/native/entry gates before invoking this."""
    from open_composer.research.ml_backend.model_factory import create_model

    dates = prepared["dates"]
    eligible = prepared["eligible"]
    output = {arm: np.full(eligible.shape, np.nan) for arm in ARMS[:-1]}
    audits = []
    for fold in monthly_folds(dates, eligible, prepared["labels"], prepared["maturity"]):
        trd, trj, weight = fold["train_d"], fold["train_j"], fold["weights"]
        evaluation_d = fold["evaluation_d"]
        ei, ej = np.where(eligible[evaluation_d])
        ed = evaluation_d[ei]
        fingerprint = hashlib.sha256(
            np.column_stack([trd, trj]).tobytes() + weight.tobytes()
        ).hexdigest()
        base = dict(
            month=fold["month"],
            cutoff=str(dates[fold["cutoff"]]),
            supported=bool(fold["supported"]),
            train_rows=len(trd),
            train_dates=len(np.unique(trd)),
            train_episodes=len(np.unique(trj)),
            included_ID_weight_sha256=fingerprint,
            selected_calendar_dates=fold["calendar_dates"].tolist(),
            latest_training_label_end=(
                str(dates[prepared["maturity"][trd].max()]) if len(trd) else None
            ),
            evaluation_rows=len(ed),
            no_hyperparameter_selection=True,
        )
        if not fold["supported"]:
            audits.append(dict(base, status="unsupported_month_missing_scores_cash"))
            record_fit(dict(base, status="unsupported_month_missing_scores_cash"))
            continue
        for arm in ARMS[:-1]:
            family = arm.split("_")[0]
            augmented = arm.endswith("STATE")
            data = prepared["state"] if augmented else prepared["stock"]
            feature_names = (
                (
                    STOCK
                    + STATE
                    + INTERACTIONS
                    + ["missing_" + name for name in STATE + INTERACTIONS]
                )
                if augmented
                else STOCK
            )
            train, test, medians = impute_training(
                data[trd, trj], data[ed, ej], state_arm=augmented
            )
            params = plan["models"][family].copy()
            params.pop("weighted_standard_scale_train_only", None)
            config = SimpleNamespace(
                model=SimpleNamespace(
                    kind="ridge_regressor" if family == "RIDGE" else "lightgbm_regressor",
                    hyperparameters=params,
                    training=SimpleNamespace(seed=20261016),
                )
            )
            invocation = dict(
                base,
                arm=arm,
                columns=train.shape[1],
                feature_order=feature_names,
                parameters=params,
            )
            record_fit(dict(invocation, status="started"))
            model = create_model(config)
            if family == "RIDGE":
                model.fit(
                    train,
                    prepared["labels"][trd, trj],
                    scale__sample_weight=weight,
                    model__sample_weight=weight,
                )
            else:
                model.fit(train, prepared["labels"][trd, trj], sample_weight=weight)
            prediction = model.predict(test) if len(test) else np.asarray([])
            if not np.isfinite(prediction).all():
                raise ValueError("Nonfinite fitted forecast; no completed account")
            output[arm][ed, ej] = prediction
            model_binding = save_model(fold["month"], arm, model)
            audit = dict(
                invocation,
                status="completed",
                medians=medians.tolist(),
                model_binding=model_binding,
            )
            if family == "RIDGE":
                audit["scaler_mean"] = model.named_steps["scale"].mean_.tolist()
                audit["scaler_scale"] = model.named_steps["scale"].scale_.tolist()
                audit["coefficients"] = model.named_steps["model"].coef_.tolist()
                audit["intercept"] = float(model.named_steps["model"].intercept_)
            else:
                audit["feature_importance_split"] = model.feature_importances_.tolist()
            audits.append(audit)
            record_fit(dict(audit, status="completed"))
    return output, audits


def registration(plan, dates):
    """Static candidate/fit inventory before any estimator is instantiated."""
    months = sorted({str(day)[:7] for day in dates if "2024-01-02" <= str(day) <= "2026-09-30"})
    rows = [
        dict(month=month, arm=arm, parameters=plan["models"][arm.split("_")[0]])
        for month in months
        for arm in ARMS[:-1]
    ]
    return dict(
        expected_fits=len(rows),
        models=rows,
        cost_view_refits=0,
        policy_arms=ARMS,
        cost_views=[10, 20, 0],
        accounts=15,
        fixed_horizon=5,
        no_grid_or_selection=True,
        registration_fingerprint=hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode()
        ).hexdigest(),
    )
