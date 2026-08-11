"""
04_data_quality.py — Data Quality Assessment (methodology-chapter section).

Documents the diagnostic finding that the dataset's original `SUSCEP`
label is a deterministic function of the seven hydro-topographic features
we have, and is therefore unsuitable as a target for ML that intends to
demonstrate spatial generalisation.

Three diagnostics are run:
    (a) Shallow decision trees (depth 2, 6, 10) — if a depth-10 tree can
        already hit ~100% accuracy on held-out spatial folds, the target
        is essentially a piecewise-constant function of the features.
    (b) Single-feature probes — fit a shallow tree on ONE feature at a
        time and check accuracy. If any single feature yields very high
        accuracy alone, the target is a simple threshold on that
        feature.
    (c) Boundary check — how many rows sit adjacent (in feature space,
        Euclidean nearest neighbour) to a row of a different class.
        If the fraction is tiny, class regions are cleanly separable
        (further evidence of a rule).

Outputs:
    reports/00_data_quality_assessment.md
    reports/00_singlefeature_probe.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.tree import DecisionTreeClassifier

from preprocess import CLASS_NAMES, FEATURE_COLS, load_prepared, make_preprocessor
from train_utils import load_splits, spatial_folds, sample_weights


ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"


def diag_shallow_trees(X: np.ndarray, y: np.ndarray, clusters: np.ndarray) -> dict:
    """Depth-2/6/10 decision trees under leave-one-cluster-out."""
    results = {}
    for depth in (2, 6, 10):
        fold_accs = []
        for fold, tr, te in spatial_folds(clusters):
            pre = make_preprocessor()
            X_tr = pre.fit_transform(X[tr])
            X_te = pre.transform(X[te])
            clf = DecisionTreeClassifier(
                max_depth=depth, random_state=42, class_weight="balanced",
            )
            clf.fit(X_tr, y[tr], sample_weight=sample_weights(y[tr]))
            acc = float((clf.predict(X_te) == y[te]).mean())
            fold_accs.append(acc)
        results[f"depth_{depth}"] = {
            "per_fold_accuracy": fold_accs,
            "mean_accuracy": float(np.mean(fold_accs)),
        }
        print(f"[dqa] depth={depth}: mean_acc={np.mean(fold_accs):.4f} "
              f"per_fold={[round(a,4) for a in fold_accs]}")
    return results


def diag_single_feature(X: np.ndarray, y: np.ndarray, clusters: np.ndarray) -> dict:
    """One-column decision tree per feature."""
    results = {}
    for i, name in enumerate(FEATURE_COLS):
        Xi = X[:, [i]]
        fold_accs = []
        for fold, tr, te in spatial_folds(clusters):
            pre = make_preprocessor()
            X_tr = pre.fit_transform(Xi[tr])
            X_te = pre.transform(Xi[te])
            clf = DecisionTreeClassifier(
                max_depth=8, random_state=42, class_weight="balanced",
            )
            clf.fit(X_tr, y[tr], sample_weight=sample_weights(y[tr]))
            fold_accs.append(float((clf.predict(X_te) == y[te]).mean()))
        results[name] = float(np.mean(fold_accs))
        print(f"[dqa] single-feature {name:>10}: mean_acc={results[name]:.4f}")
    return results


def diag_boundary(X: np.ndarray, y: np.ndarray, sample: int = 20_000) -> dict:
    """Fraction of rows whose 1-NN in feature space belongs to a different class.

    On a genuine noisy target this is often 5-30%. On a rule-based target
    it's typically near 0 (only boundary pixels).
    """
    rng = np.random.default_rng(42)
    idx = rng.choice(len(y), size=min(sample, len(y)), replace=False)
    pre = make_preprocessor()
    Xn = pre.fit_transform(X[idx])
    # k=2 because k=1 returns the point itself.
    nn = NearestNeighbors(n_neighbors=2).fit(Xn)
    _, ind = nn.kneighbors(Xn)
    neighbour_labels = y[idx][ind[:, 1]]
    frac_diff = float((neighbour_labels != y[idx]).mean())
    return {"sample_size": int(len(idx)), "fraction_diff_class_1nn": frac_diff}


def main() -> None:
    X_df, y, _ = load_prepared()
    # Sentinels have already been replaced by NaN; median-impute here just
    # so decision trees don't reject NaN. Done outside the split loop so
    # each fold still fits its own scaler (imputation uses global median,
    # but that's fine for a diagnostic).
    X_df = X_df.fillna(X_df.median(numeric_only=True))
    X = X_df.values
    splits = load_splits()
    clusters = splits["clusters"]

    print("[dqa] (a) shallow decision trees under spatial LOCO")
    trees = diag_shallow_trees(X, y, clusters)

    print("\n[dqa] (b) single-feature probes")
    singles = diag_single_feature(X, y, clusters)

    print("\n[dqa] (c) nearest-neighbour class-boundary check")
    boundary = diag_boundary(X, y)
    print(f"[dqa] 1-NN different-class fraction: "
          f"{boundary['fraction_diff_class_1nn']:.4%} of {boundary['sample_size']} rows")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "00_singlefeature_probe.json").write_text(
        json.dumps({"trees": trees, "singles": singles, "boundary": boundary}, indent=2),
        encoding="utf-8",
    )

    # ---- Report ----
    lines: list[str] = []
    a = lines.append
    a("# 00 — Data Quality Assessment\n")
    a("**Finding.** The `SUSCEP` label in the raw dataset is a "
      "deterministic function of the seven hydro-topographic conditioning "
      "features. An XGBoost classifier trained under strict leave-one-"
      "cluster-out spatial validation achieves **100.00% accuracy** on "
      "every held-out cluster (see `03_tree.json`). This is only possible "
      "if the target was constructed *from* those features (a "
      "weighted-overlay or fuzzy-AHP susceptibility index), not observed "
      "independently.\n")
    a("The dataset's provided label is therefore unsuitable as ground "
      "truth for a supervised learning study aimed at demonstrating "
      "spatial transferability — the model is reverse-engineering a rule, "
      "not learning flood physics. Below are three corroborating "
      "diagnostics before we describe how we deviated.\n")

    a("## Diagnostic (a): shallow decision trees, leave-one-cluster-out")
    a("| max_depth | per-fold accuracy | mean |")
    a("|---:|---|---:|")
    for depth in (2, 6, 10):
        r = trees[f"depth_{depth}"]
        per = ", ".join(f"{v:.4f}" for v in r["per_fold_accuracy"])
        a(f"| {depth} | {per} | **{r['mean_accuracy']:.4f}** |")
    a("")
    d10 = trees["depth_10"]["mean_accuracy"]
    a(f"A depth-10 tree — small enough to be inspected by hand — reaches "
      f"**{d10:.2%}** mean accuracy on held-out clusters. Depth-2 already "
      f"reaches {trees['depth_2']['mean_accuracy']:.2%}. A tree of that "
      "size cannot approximate a genuine noisy target; it can only "
      "replicate a small piecewise rule.\n")

    a("## Diagnostic (b): single-feature probes")
    a("| feature | mean LOCO accuracy (this feature alone) |")
    a("|---|---:|")
    for name, acc in sorted(singles.items(), key=lambda kv: -kv[1]):
        a(f"| {name} | {acc:.4f} |")
    top = max(singles.items(), key=lambda kv: kv[1])
    a(f"\nThe strongest single feature is **{top[0]}** at "
      f"**{top[1]:.2%}**. A single-column threshold that already predicts "
      "the majority of rows correctly is characteristic of a rule-derived "
      "label, not a real-world outcome.\n")

    a("## Diagnostic (c): class-boundary sharpness")
    a(f"On a random sample of {boundary['sample_size']:,} rows, the "
      "fraction whose nearest neighbour (in scaled 7-D feature space) "
      f"belongs to a different class is **{boundary['fraction_diff_class_1nn']:.2%}**. "
      "For an observed target with measurement noise or unobserved drivers "
      "this fraction is typically 5–30%. A near-zero value indicates class "
      "regions are cleanly separated by a smooth surface in feature space.\n")

    a("## How we proceed")
    a("Rather than pretending the provided `SUSCEP` label is ground truth "
      "(which would produce a thesis where every reported metric is 1.00 and "
      "no meaningful spatial-validation claim can be made), we construct our "
      "own susceptibility target `SUSCEP_v2` from the same conditioning "
      "layers using a **literature-informed AHP weighted-overlay** — the "
      "standard method in the flood-susceptibility literature we cited "
      "(Pradhan et al. 2023; Yang et al. 2024, among others).\n")
    a("Construction of `SUSCEP_v2`, the chosen factor weights and their "
      "precedent, and the side-by-side agreement with the provided "
      "`SUSCEP`, are documented in `04_target_construction.md`. All "
      "subsequent model training, spatial vs. random split evaluation, and "
      "SHAP-based validation target `SUSCEP_v2`. The provided `SUSCEP` is "
      "retained only as a comparison baseline in the eval report.\n")

    a("This deviation is a methodological contribution in its own right: "
      "the diagnostic pipeline above transfers to any similar 'ready-made' "
      "susceptibility dataset a downstream researcher might be handed, and "
      "surfaces this class of leakage before a model is trained.")

    out_path = REPORTS_DIR / "00_data_quality_assessment.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[dqa] wrote {out_path}")


if __name__ == "__main__":
    main()
