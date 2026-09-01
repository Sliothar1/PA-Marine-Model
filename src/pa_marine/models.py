from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def _try_lgbm():
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            class_weight="balanced",
        )
    except Exception:
        return None


def _try_xgb():
    try:
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
            n_jobs=4,
        )
    except Exception:
        return None


def _hgb():
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.06,
        max_iter=200,
        random_state=42,
    )


def make_estimators() -> dict[str, Any]:
    est = {
        "logreg": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("clf", LogisticRegression(max_iter=400, class_weight="balanced")),
            ]
        )
    }
    lgbm = _try_lgbm()
    xgb = _try_xgb()
    if lgbm is not None:
        est["lightgbm"] = lgbm
    elif xgb is not None:
        est["xgboost"] = xgb
    else:
        est["hist_gbdt"] = _hgb()
    return est


def fit_predict(est, X_train, y_train, X_eval) -> np.ndarray:
    est.fit(X_train, y_train)
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X_eval)[:, 1]
    d = est.decision_function(X_eval)
    return 1 / (1 + np.exp(-d))
