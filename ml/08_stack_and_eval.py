"""
08_stack_and_eval.py — Stack the tree branch (XGBoost) and the DNN branch
via a logistic-regression meta-learner, then produce the final side-by-
side spatial-vs-random evaluation report.

Stacking design:
  Base features for the meta-learner are the two branches' class
  probability vectors, concatenated: shape (N, 2 * n_classes) = (N, 10).
  Fitting the meta-learner on IN-SAMPLE base predictions leaks; we use
  each branch's out-of-fold (OOF) predictions instead — this is the
  standard "stacked generalization" recipe (Wolpert 1992).

Two evaluation regimes:
  1. Spatial LOCO. Each row's meta features are its two branches' OOF
     predictions from the fold in which it was held out. The meta-learner
     is fit under a fresh 5-fold LOCO on those OOF features to keep the
     evaluation honest (no data ever seen at train time by any layer).
  2. Random 80/20. Meta-learner is trained on branch predictions over the
     random training set (using the branches trained on that split) and
     evaluated on the held-out 20%.

Outputs:
    data/processed/stack_oof_spatial.npz     final stacked OOF preds
    data/processed/stack_random_preds.npz    stacked random-split preds
    models/stack_meta.joblib                 fitted meta-learner + coefs
    reports/05_model_eval.md                 headline eval report
    reports/05_confusion_*.png               confusion matrices
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from preprocess import CLASS_NAMES
from train_utils import metric_bundle


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"


def load_oof_pair() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return tree OOF probs, dnn OOF probs, y, fold ids — all under spatial LOCO."""
    t = np.load(PROCESSED_DIR / "tree_v2_oof_spatial.npz")
    d = np.load(PROCESSED_DIR / "dnn_v2_oof_spatial.npz")
    assert (t["y"] == d["y"]).all(), "tree/dnn OOF have different y"
    assert (t["oof_fold"] == d["oof_fold"]).all(), "tree/dnn OOF fold assignments differ"
    return t["oof_proba"], d["oof_proba"], t["y"], t["oof_fold"]


def stack_spatial() -> tuple[np.ndarray, np.ndarray, dict]:
    """Meta-learner LOCO'd across the same 5 folds as the base branches."""
    tree_p, dnn_p, y, fold = load_oof_pair()
    Z = np.concatenate([tree_p, dnn_p], axis=1)  # (N, 10)

    meta_pred = np.zeros_like(y)
    meta_proba = np.zeros((len(y), len(CLASS_NAMES)), dtype=np.float32)
    n_folds = int(fold.max()) + 1
    for k in range(n_folds):
        tr = np.where(fold != k)[0]
        te = np.where(fold == k)[0]
        meta = LogisticRegression(
            max_iter=500, C=1.0,
            class_weight="balanced", solver="lbfgs",
        )
        meta.fit(Z[tr], y[tr])
        meta_pred[te] = meta.predict(Z[te])
        meta_proba[te] = meta.predict_proba(Z[te]).astype(np.float32)

    m = metric_bundle(y, meta_pred)
    np.savez_compressed(
        PROCESSED_DIR / "stack_oof_spatial.npz",
        proba=meta_proba, pred=meta_pred, y=y, fold=fold,
    )
    return meta_pred, y, m


def stack_random() -> tuple[np.ndarray, np.ndarray, dict, LogisticRegression]:
    """Meta-learner trained on the base predictions over the random test set.

    Base branches under the random regime already saved their test-set
    predictions; we split those into meta-train / meta-eval via a
    stratified 5-fold CV so the meta-learner never sees rows it's judged on.
    Then we report the pooled OOF metric.
    """
    t = np.load(PROCESSED_DIR / "tree_v2_random_preds.npz")
    d = np.load(PROCESSED_DIR / "dnn_v2_random_preds.npz")
    assert (t["y"] == d["y"]).all()
    assert (t["test_idx"] == d["test_idx"]).all()
    y = t["y"]
    Z = np.concatenate([t["proba"], d["proba"]], axis=1)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    meta_pred = np.zeros_like(y)
    meta_proba = np.zeros((len(y), len(CLASS_NAMES)), dtype=np.float32)
    for tr, te in skf.split(Z, y):
        meta = LogisticRegression(
            max_iter=500, C=1.0,
            class_weight="balanced", solver="lbfgs",
        )
        meta.fit(Z[tr], y[tr])
        meta_pred[te] = meta.predict(Z[te])
        meta_proba[te] = meta.predict_proba(Z[te]).astype(np.float32)

    m = metric_bundle(y, meta_pred)

    # Fit a single meta on all random-test base preds for the final
    # serve-time stack (used with the full-data base models).
    final_meta = LogisticRegression(
        max_iter=500, C=1.0,
        class_weight="balanced", solver="lbfgs",
    ).fit(Z, y)

    np.savez_compressed(
        PROCESSED_DIR / "stack_random_preds.npz",
        proba=meta_proba, pred=meta_pred, y=y,
    )
    return meta_pred, y, m, final_meta


def plot_confusion(cm: np.ndarray, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(CLASS_NAMES))); ax.set_yticks(range(len(CLASS_NAMES)))
    ax.set_xticklabels(CLASS_NAMES, rotation=45, ha="right")
    ax.set_yticklabels(CLASS_NAMES)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    ax.set_title(title)
    vmax = cm.max()
    for i in range(len(CLASS_NAMES)):
        for j in range(len(CLASS_NAMES)):
            ax.text(j, i, f"{cm[i,j]:,}", ha="center", va="center",
                    fontsize=8, color=("white" if cm[i,j] > vmax/2 else "black"))
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=140); plt.close(fig)


def load_branch_summaries() -> dict:
    return {
        "tree": json.loads((REPORTS_DIR / "06_tree_v2.json").read_text())["summary"],
        "dnn":  json.loads((REPORTS_DIR / "07_dnn_v2.json").read_text())["summary"],
    }


def main() -> None:
    print("[stack] spatial LOCO stacking")
    sp_pred, sp_y, sp_m = stack_spatial()
    print(f"  stack SPATIAL: acc={sp_m['accuracy']:.4f} "
          f"f1_macro={sp_m['f1_macro']:.4f} f1_w={sp_m['f1_weighted']:.4f}")

    print("[stack] random-split stacking")
    rn_pred, rn_y, rn_m, final_meta = stack_random()
    print(f"  stack RANDOM:  acc={rn_m['accuracy']:.4f} "
          f"f1_macro={rn_m['f1_macro']:.4f} f1_w={rn_m['f1_weighted']:.4f}")

    import joblib
    joblib.dump({"meta": final_meta,
                 "coef_shape": final_meta.coef_.shape,
                 "n_features_in": final_meta.n_features_in_,
                 "class_names": list(CLASS_NAMES)},
                MODELS_DIR / "stack_meta.joblib")

    # Confusion matrices
    plot_confusion(np.array(sp_m["confusion"]),
                   f"Stacked model — spatial LOCO (acc {sp_m['accuracy']:.2%})",
                   REPORTS_DIR / "05_confusion_spatial.png")
    plot_confusion(np.array(rn_m["confusion"]),
                   f"Stacked model — random 80/20 (acc {rn_m['accuracy']:.2%})",
                   REPORTS_DIR / "05_confusion_random.png")

    branch = load_branch_summaries()

    # ---- Report ----
    lines: list[str] = []
    a = lines.append
    a("# 05 — Model evaluation (SUSCEP_v2)\n")
    a("Target: `SUSCEP_v2` (constructed AHP-weighted overlay of all 7 "
      "conditioning factors — see `04_target_construction.md`).\n")
    a("## Headline numbers")
    a("| Model | Split | Accuracy | F1 macro | F1 weighted |")
    a("|---|---|---:|---:|---:|")
    for model_name, key in [("XGBoost", "tree"), ("DNN (MLP)", "dnn"),
                            ("Stacked", None)]:
        if key is None:
            a(f"| **Stacked** | Spatial LOCO | **{sp_m['accuracy']:.4f}** "
              f"| **{sp_m['f1_macro']:.4f}** | **{sp_m['f1_weighted']:.4f}** |")
            a(f"| **Stacked** | Random 80/20 | **{rn_m['accuracy']:.4f}** "
              f"| **{rn_m['f1_macro']:.4f}** | **{rn_m['f1_weighted']:.4f}** |")
        else:
            s = branch[key]
            a(f"| {model_name} | Spatial LOCO | {s['spatial_overall_accuracy']:.4f} "
              f"| {s['spatial_overall_f1_macro']:.4f} | {s['spatial_overall_f1_weighted']:.4f} |")
            a(f"| {model_name} | Random 80/20 | {s['random_accuracy']:.4f} "
              f"| {s['random_f1_macro']:.4f} | {s['random_f1_weighted']:.4f} |")
    a("")
    a("## Spatial-vs-random gap (the honest number)")
    gap_acc = rn_m["accuracy"] - sp_m["accuracy"]
    gap_f1 = rn_m["f1_macro"] - sp_m["f1_macro"]
    a("| Metric | Random | Spatial | Random − Spatial |")
    a("|---|---:|---:|---:|")
    a(f"| Accuracy | {rn_m['accuracy']:.4f} | {sp_m['accuracy']:.4f} | **{gap_acc:+.4f}** |")
    a(f"| F1 macro | {rn_m['f1_macro']:.4f} | {sp_m['f1_macro']:.4f} | **{gap_f1:+.4f}** |")
    a("")
    a("A non-zero gap is the entire point of the leave-one-cluster-out "
      "protocol: it quantifies how much of the model's accuracy on the "
      "random split was due to memorising local geographic patterns "
      "rather than learning transferable factor combinations. Under the "
      "original (Drainage-only) `SUSCEP` this gap was 0.0000 (see "
      "`03_tree.json`) because the target was a trivial univariate rule.\n")
    a("## Confusion matrices")
    a("![spatial](05_confusion_spatial.png)")
    a("![random](05_confusion_random.png)")
    a("")
    a("## Notes on methodology")
    a("- Base branches are trained on the same folds (persisted in "
      "`splits.npz`) with identical preprocessing fit *inside* each fold.")
    a("- The stacked meta-learner is a class-weighted multinomial logistic "
      "regression on the concatenated 10-dim (2 branches × 5 classes) "
      "probability vector.")
    a("- Under spatial LOCO the meta-learner itself is trained under a "
      "second pass of LOCO so the reported number reflects a model that "
      "has never seen any data from the cluster it's judged on, at "
      "either layer.")

    (REPORTS_DIR / "05_model_eval.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[stack] wrote {REPORTS_DIR / '05_model_eval.md'}")


if __name__ == "__main__":
    main()
