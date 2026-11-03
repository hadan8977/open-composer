"""Shared mature monthly rows and one fixed weighted Ridge; no fit on import."""

import hashlib
from types import SimpleNamespace

import numpy as np
from method import train_design


def fold(z, current):
    permitted = (
        (z["entry"] < z["entry"][current])
        & (z["label_end"] >= 0)
        & (z["label_end"] < z["entry"][current])
    )
    rows = np.flatnonzero(permitted)
    ii, jj = np.where(z["eligible"][rows] & np.isfinite(z["label"][rows]))
    ii = rows[ii]
    weights = np.zeros(len(ii))
    for date in np.unique(ii):
        weights[ii == date] = 1 / np.sum(ii == date)
    supported_t = np.isfinite(z["turnover"][ii, jj])
    ready = (
        len(ii) >= 400
        and len(np.unique(ii)) >= 24
        and len(np.unique(jj)) >= 12
        and int(supported_t.sum()) >= 200
        and len(np.unique(ii[supported_t])) >= 18
        and len(np.unique(jj[supported_t])) >= 8
    )
    ids = [str(z["months"][i]) + ":" + str(z["symbols"][j]) for i, j in zip(ii, jj, strict=True)]
    return dict(
        i=ii,
        j=jj,
        weights=weights,
        IDs=ids,
        IDs_sha256=hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        weights_sha256=hashlib.sha256(weights.astype("<f8").tobytes()).hexdigest(),
        supported=bool(ready),
        rows=len(ii),
        months=len(np.unique(ii)),
        symbols=len(np.unique(jj)),
        turnover_rows=int(supported_t.sum()),
        turnover_months=len(np.unique(ii[supported_t])),
        turnover_symbols=len(np.unique(jj[supported_t])),
    )


def fit_pair(z, current, ledger):
    f = fold(z, current)
    predictions = {p: np.full(len(z["symbols"]), np.nan) for p in ["BASE", "AUG"]}
    if not f["supported"]:
        return predictions, dict(
            supported=False, fold={k: v for k, v in f.items() if k not in ["i", "j", "weights"]}
        )
    ii, jj, weights = f["i"], f["j"], f["weights"]
    train_base, train_aug, primitive_state = train_design(
        z["primitive"][ii, jj],
        z["flags"][ii, jj],
        z["turnover"][ii, jj],
        weights,
    )
    current_base, current_aug, _ = train_design(
        z["primitive"][current],
        z["flags"][current],
        z["turnover"][current],
        np.ones(len(z["symbols"])),
        state=primitive_state,
    )
    from open_composer.research.ml_backend.model_factory import create_model

    models = {}
    target = z["label"][ii, jj]
    for policy, train, test in [
        ("BASE", train_base, current_base),
        ("AUG", train_aug, current_aug),
    ]:
        trial = f"fit:{z['context']}:{z['months'][current]}:{policy}"
        ledger(trial, "STARTED")
        spec = SimpleNamespace(
            model=SimpleNamespace(
                kind="ridge_regressor",
                hyperparameters=dict(alpha=10.0, fit_intercept=True),
                training=SimpleNamespace(seed=20261017),
            )
        )
        estimator = create_model(spec)
        estimator.fit(train, target, scale__sample_weight=weights, model__sample_weight=weights)
        predictions[policy] = estimator.predict(test)
        scaler, ridge = estimator.named_steps["scale"], estimator.named_steps["model"]
        models[policy] = dict(
            mean=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),
            coef=ridge.coef_.tolist(),
            intercept=float(ridge.intercept_),
            alpha=10.0,
            feature_count=train.shape[1],
            prediction=predictions[policy].tolist(),
            trial_id=trial,
        )
        ledger(
            trial,
            "COMPLETED",
            dict(
                primitive_state=primitive_state,
                model=models[policy],
                fold={k: v for k, v in f.items() if k not in ["i", "j", "weights"]},
            ),
        )
    supported_t = np.isfinite(z["turnover"][current])
    before = predictions["AUG"].copy()
    predictions["AUG"][~supported_t] = predictions["BASE"][~supported_t]
    return predictions, dict(
        supported=True,
        fold={k: v for k, v in f.items() if k not in ["i", "j", "weights"]},
        primitive_state=primitive_state,
        models=models,
        augmented_before_exact_fallback=before.tolist(),
        current_exact_BASE_fallback=(~supported_t).tolist(),
        target_basis=(
            "Operating capital net hypothetical10bp each side, separate gross CVR claims/bounds"
        ),
    )
