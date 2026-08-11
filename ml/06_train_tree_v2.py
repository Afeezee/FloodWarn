"""
06_train_tree_v2.py — Train XGBoost tree branch on SUSCEP_v2 under both
split regimes. Structure mirrors 03_train_tree.py but targets the
constructed label from susceptibility_v2.npz.

Outputs:
    models/tree_v2_spatial_fold{k}.json      per-fold spatial models
    models/tree_v2_random.json               random-split model
    models/tree_v2_full.json                 all-data model for serve-time
    data/processed/tree_v2_oof_spatial.npz   OOF probs for stacking
    data/processed/tree_v2_random_preds.npz  random-split predictions
    reports/06_tree_v2.json                  metrics under both regimes
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb

from preprocess import CLASS_NAMES, FEATURE_COLS, load_prepared, make_preprocessor
from train_utils import load_splits, spatial_folds, sample_weights, metric_bundle


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

N_CLASSES = len(CLASS_NAMES)

XGB_PARAMS = dict(
    objective="multi:softprob",
    num_class=N_CLASSES,
    eval_metric="mlogloss",
    tree_method="hist",
    max_depth=6,               # was 8 — smaller trees, faster fitting
    learning_rate=0.1,         # was 0.05 — compensate for fewer rounds
    subsample=0.85,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    seed=42,
    verbosity=0,
    nthread=0,                 # use all available cores
)
NUM_BOOST_ROUND = 250          # was 600
EARLY_STOP = 20


def load_v2_target() -> np.ndarray:
    z = np.load(PROCESSED_DIR / "susceptibility_v2.npz")
    return z["class_v2"].astype(np.int64)


def _train_one(X_tr, y_tr, w_tr, X_te, y_te, w_te):
    dtr = xgb.DMatrix(X_tr, label=y_tr, weight=w_tr)
    dte = xgb.DMatrix(X_te, label=y_te, weight=w_te)
    booster = xgb.train(
        XGB_PARAMS, dtr,
        num_boost_round=NUM_BOOST_ROUND,
        evals=[(dtr, "train"), (dte, "test")],
        early_stopping_rounds=EARLY_STOP,
        verbose_eval=False,
    )
    return booster, booster.predict(dte), booster.best_iteration


def main() -> None:
    for d in (MODELS_DIR, PROCESSED_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    X_df, _y_orig, _ = load_prepared()
    X = X_df.values
    y = load_v2_target()
    splits = load_splits()

    results = {"features": list(FEATURE_COLS), "params": XGB_PARAMS, "target": "SUSCEP_v2"}

    # ---- Spatial LOCO ----
    print("[tree_v2] SPATIAL leave-one-cluster-out")
    fold_metrics = []
    oof_proba = np.zeros((len(y), N_CLASSES), dtype=np.float32)
    oof_pred = np.full(len(y), -1, dtype=np.int64)
    oof_fold = np.full(len(y), -1, dtype=np.int64)
    best_iters = []

    t0 = time.time()
    for fold, tr_idx, te_idx in spatial_folds(splits["clusters"]):
        pre = make_preprocessor()
        X_tr = pre.fit_transform(X[tr_idx]); X_te = pre.transform(X[te_idx])
        y_tr, y_te = y[tr_idx], y[te_idx]
        w_tr, w_te = sample_weights(y_tr), sample_weights(y_te)

        booster, proba, best_it = _train_one(X_tr, y_tr, w_tr, X_te, y_te, w_te)
        pred = proba.argmax(axis=1)
        m = metric_bundle(y_te, pred)
        m["fold"] = fold; m["n_test"] = int(len(te_idx))
        m["best_iteration"] = int(best_it)
        fold_metrics.append(m)
        best_iters.append(best_it)
        print(f"  fold {fold}: n={len(te_idx):,} acc={m['accuracy']:.4f} "
              f"f1_macro={m['f1_macro']:.4f} best_it={best_it}")

        oof_proba[te_idx] = proba.astype(np.float32)
        oof_pred[te_idx] = pred
        oof_fold[te_idx] = fold

        booster.save_model(str(MODELS_DIR / f"tree_v2_spatial_fold{fold}.json"))

    spatial_overall = metric_bundle(y, oof_pred)
    print(f"  OVERALL spatial (OOF): acc={spatial_overall['accuracy']:.4f} "
          f"f1_macro={spatial_overall['f1_macro']:.4f}")
    print(f"[tree_v2] spatial regime done in {time.time()-t0:.1f}s")

    np.savez_compressed(
        PROCESSED_DIR / "tree_v2_oof_spatial.npz",
        oof_proba=oof_proba, oof_pred=oof_pred, oof_fold=oof_fold, y=y,
    )
    results["spatial"] = {"per_fold": fold_metrics, "overall_oof": spatial_overall}

    # ---- Random split ----
    print("[tree_v2] RANDOM stratified 80/20")
    tr_idx = splits["random_train_idx"]; te_idx = splits["random_test_idx"]
    pre = make_preprocessor()
    X_tr = pre.fit_transform(X[tr_idx]); X_te = pre.transform(X[te_idx])
    y_tr, y_te = y[tr_idx], y[te_idx]
    w_tr, w_te = sample_weights(y_tr), sample_weights(y_te)

    t0 = time.time()
    booster, proba, best_it = _train_one(X_tr, y_tr, w_tr, X_te, y_te, w_te)
    pred = proba.argmax(axis=1)
    random_metrics = metric_bundle(y_te, pred)
    random_metrics["best_iteration"] = int(best_it)
    print(f"  RANDOM: acc={random_metrics['accuracy']:.4f} "
          f"f1_macro={random_metrics['f1_macro']:.4f}  best_it={best_it}  "
          f"({time.time()-t0:.1f}s)")

    booster.save_model(str(MODELS_DIR / "tree_v2_random.json"))
    np.savez_compressed(
        PROCESSED_DIR / "tree_v2_random_preds.npz",
        proba=proba.astype(np.float32), pred=pred, y=y_te, test_idx=te_idx,
    )
    results["random"] = random_metrics

    # ---- Full-data fit for serve-time ----
    print("[tree_v2] FULL-data fit")
    pre_full = make_preprocessor()
    X_full = pre_full.fit_transform(X)
    w_full = sample_weights(y)
    dfull = xgb.DMatrix(X_full, label=y, weight=w_full)
    n_rounds = int(np.median(best_iters)) if best_iters else NUM_BOOST_ROUND // 2
    n_rounds = max(50, n_rounds)
    t0 = time.time()
    booster_full = xgb.train(XGB_PARAMS, dfull, num_boost_round=n_rounds)
    booster_full.save_model(str(MODELS_DIR / "tree_v2_full.json"))
    joblib.dump(
        {"pipeline": pre_full, "feature_cols": list(FEATURE_COLS),
         "class_names": list(CLASS_NAMES), "target": "SUSCEP_v2"},
        MODELS_DIR / "preprocess_v2_fullfit.joblib",
    )
    print(f"[tree_v2] full fit done in {time.time()-t0:.1f}s ({n_rounds} rounds)")

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
    print("[tree_v2] summary:", json.dumps(results["summary"], indent=2))

    (REPORTS_DIR / "06_tree_v2.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(f"[tree_v2] wrote {REPORTS_DIR / '06_tree_v2.json'}")


if __name__ == "__main__":
    main()
