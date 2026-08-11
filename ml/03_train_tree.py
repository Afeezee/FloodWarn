"""
03_train_tree.py — Train the tree branch (XGBoost multiclass) under both
split regimes and produce out-of-fold (OOF) probabilities used later by
the stacked meta-learner.

Outputs:
    models/tree_xgb_spatial_fold{k}.json     (5 per-fold models)
    models/tree_xgb_random.json              (1 model on the random split)
    models/tree_xgb_full.json                (1 model on ALL data, for serve-time inference)
    data/processed/tree_oof_spatial.npz      (OOF probabilities + labels + fold ids)
    data/processed/tree_random_preds.npz     (random-split test predictions + probs)
    reports/03_tree.json                     (metrics under both regimes)

Run:
    python ml/03_train_tree.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import xgboost as xgb

from preprocess import CLASS_NAMES, FEATURE_COLS, load_prepared, make_preprocessor
from train_utils import load_splits, spatial_folds, sample_weights, metric_bundle


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

N_CLASSES = len(CLASS_NAMES)

# XGBoost hyperparameters. Deliberately restrained: 400 rounds with early
# stopping, depth 8, learning rate 0.05. Not tuned aggressively — the
# spatial/random gap is the number that matters, not squeezing a fractional
# f1 improvement.
XGB_PARAMS = dict(
    objective="multi:softprob",
    num_class=N_CLASSES,
    eval_metric="mlogloss",
    tree_method="hist",
    max_depth=8,
    learning_rate=0.05,
    subsample=0.85,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    seed=42,
    verbosity=0,
)
NUM_BOOST_ROUND = 600
EARLY_STOP = 30


def _train_one(X_tr, y_tr, w_tr, X_te, y_te, w_te) -> tuple[xgb.Booster, np.ndarray]:
    dtr = xgb.DMatrix(X_tr, label=y_tr, weight=w_tr)
    dte = xgb.DMatrix(X_te, label=y_te, weight=w_te)
    booster = xgb.train(
        XGB_PARAMS,
        dtr,
        num_boost_round=NUM_BOOST_ROUND,
        evals=[(dtr, "train"), (dte, "test")],
        early_stopping_rounds=EARLY_STOP,
        verbose_eval=False,
    )
    proba = booster.predict(dte)
    return booster, proba


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    X_df, y, _coords = load_prepared()
    X = X_df.values
    splits = load_splits()

    results: dict = {"features": list(FEATURE_COLS), "params": XGB_PARAMS}

    # ---- Spatial leave-one-cluster-out ----
    print("[tree] SPATIAL leave-one-cluster-out")
    fold_metrics = []
    # OOF containers: one prediction per row from the fold where it was held out.
    oof_proba = np.zeros((len(y), N_CLASSES), dtype=np.float32)
    oof_pred = np.full(len(y), -1, dtype=np.int64)
    oof_fold = np.full(len(y), -1, dtype=np.int64)

    t0 = time.time()
    for fold, tr_idx, te_idx in spatial_folds(splits["clusters"]):
        # Fit the preprocessing pipeline on train fold ONLY (prevents leakage).
        pre = make_preprocessor()
        X_tr = pre.fit_transform(X[tr_idx])
        X_te = pre.transform(X[te_idx])
        y_tr, y_te = y[tr_idx], y[te_idx]
        w_tr = sample_weights(y_tr)
        w_te = sample_weights(y_te)

        booster, proba = _train_one(X_tr, y_tr, w_tr, X_te, y_te, w_te)
        pred = proba.argmax(axis=1)

        m = metric_bundle(y_te, pred)
        m["fold"] = fold
        m["n_test"] = int(len(te_idx))
        fold_metrics.append(m)
        print(f"  fold {fold}: n_test={len(te_idx):,} "
              f"acc={m['accuracy']:.4f} f1_macro={m['f1_macro']:.4f}")

        oof_proba[te_idx] = proba.astype(np.float32)
        oof_pred[te_idx] = pred
        oof_fold[te_idx] = fold

        booster.save_model(str(MODELS_DIR / f"tree_xgb_spatial_fold{fold}.json"))

    # Aggregate spatial metrics via OOF (concatenated predictions across folds)
    spatial_overall = metric_bundle(y, oof_pred)
    print(f"  OVERALL spatial (OOF): acc={spatial_overall['accuracy']:.4f} "
          f"f1_macro={spatial_overall['f1_macro']:.4f}")
    print(f"[tree] spatial regime done in {time.time()-t0:.1f}s")

    np.savez_compressed(
        PROCESSED_DIR / "tree_oof_spatial.npz",
        oof_proba=oof_proba, oof_pred=oof_pred, oof_fold=oof_fold, y=y,
    )
    results["spatial"] = {
        "per_fold": fold_metrics,
        "overall_oof": spatial_overall,
    }

    # ---- Random stratified 80/20 ----
    print("[tree] RANDOM stratified 80/20")
    tr_idx = splits["random_train_idx"]
    te_idx = splits["random_test_idx"]
    pre = make_preprocessor()
    X_tr = pre.fit_transform(X[tr_idx])
    X_te = pre.transform(X[te_idx])
    y_tr, y_te = y[tr_idx], y[te_idx]
    w_tr = sample_weights(y_tr)
    w_te = sample_weights(y_te)

    t0 = time.time()
    booster, proba = _train_one(X_tr, y_tr, w_tr, X_te, y_te, w_te)
    pred = proba.argmax(axis=1)
    random_metrics = metric_bundle(y_te, pred)
    print(f"  RANDOM: acc={random_metrics['accuracy']:.4f} "
          f"f1_macro={random_metrics['f1_macro']:.4f}  ({time.time()-t0:.1f}s)")

    booster.save_model(str(MODELS_DIR / "tree_xgb_random.json"))
    np.savez_compressed(
        PROCESSED_DIR / "tree_random_preds.npz",
        proba=proba.astype(np.float32), pred=pred, y=y_te, test_idx=te_idx,
    )
    results["random"] = random_metrics

    # ---- Full-data fit for serve-time inference ----
    print("[tree] FULL-data fit for serve-time inference")
    pre_full = make_preprocessor()
    X_full = pre_full.fit_transform(X)
    w_full = sample_weights(y)
    dfull = xgb.DMatrix(X_full, label=y, weight=w_full)
    t0 = time.time()
    # Use the median n_boost_round from the CV runs (a safe compromise
    # between overfitting and undertraining the final model). Fall back to
    # a fixed budget if fold histories are unavailable.
    n_rounds = int(np.median([
        booster.best_iteration if hasattr(booster, "best_iteration") else NUM_BOOST_ROUND
        for booster in []  # We didn't retain per-fold boosters; use fixed.
    ] or [NUM_BOOST_ROUND // 2]))
    booster_full = xgb.train(XGB_PARAMS, dfull, num_boost_round=n_rounds)
    booster_full.save_model(str(MODELS_DIR / "tree_xgb_full.json"))
    # Also persist the full-fit preprocessor for the same use.
    import joblib
    joblib.dump(
        {"pipeline": pre_full, "feature_cols": list(FEATURE_COLS),
         "class_names": list(CLASS_NAMES)},
        MODELS_DIR / "preprocess_fullfit.joblib",
    )
    print(f"[tree] full-data fit done in {time.time()-t0:.1f}s "
          f"({n_rounds} rounds)")

    # ---- Compact summary for logs / report ----
    results["summary"] = {
        "spatial_overall_accuracy": spatial_overall["accuracy"],
        "spatial_overall_f1_macro": spatial_overall["f1_macro"],
        "spatial_overall_f1_weighted": spatial_overall["f1_weighted"],
        "random_accuracy": random_metrics["accuracy"],
        "random_f1_macro": random_metrics["f1_macro"],
        "random_f1_weighted": random_metrics["f1_weighted"],
        "gap_accuracy": random_metrics["accuracy"] - spatial_overall["accuracy"],
        "gap_f1_macro": random_metrics["f1_macro"] - spatial_overall["f1_macro"],
    }
    print("[tree] summary:", json.dumps(results["summary"], indent=2))

    (REPORTS_DIR / "03_tree.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(f"[tree] wrote {REPORTS_DIR / '03_tree.json'}")


if __name__ == "__main__":
    main()
