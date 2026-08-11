"""
09_shap_explain.py — Run SHAP on the full-data XGBoost model targeting
SUSCEP_v2, both as (a) a validation of the AHP construction (do the
recovered SHAP importances track the assigned weights?) and (b) the
per-point explanation layer served in the app.

Two products:
    reports/08_shap_validation.md     mean-|SHAP| ranking vs assigned weights,
                                       + plots
    ml/explain.py                     the runtime function used by the Next.js
                                       API: given a point's SHAP values and
                                       feature values, produce a short
                                       plain-language explanation and the top-N
                                       contributing factors.

The precomputed layer in Task 17 calls into `explain.py` for every grid
point and stores the resulting text so serve-time inference is a pure
lookup.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from preprocess import CLASS_NAMES, FEATURE_COLS, load_prepared


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

# Weights we assigned when constructing SUSCEP_v2. Kept in sync with
# 05_construct_target.py — if you change them there, update here too.
ASSIGNED_WEIGHTS = {
    "TWI": 0.22, "Slope": 0.20, "Rainfall": 0.18, "FA": 0.15,
    "Drainage": 0.12, "Curvature": 0.08, "Aspect": 0.05,
}


def main() -> None:
    print("[shap] loading full-data XGBoost model")
    booster = xgb.Booster()
    booster.load_model(str(MODELS_DIR / "tree_v2_full.json"))

    pre_bundle = joblib.load(MODELS_DIR / "preprocess_v2_fullfit.joblib")
    pre = pre_bundle["pipeline"]

    X_df, _, coords = load_prepared()
    X = pre.transform(X_df.values)

    # SHAP over a random subsample — full 144K × 7 × 5-class SHAP is heavy
    # and unnecessary for the aggregate validation. Sample 20K.
    rng = np.random.default_rng(42)
    idx = rng.choice(len(X), size=20_000, replace=False)
    print(f"[shap] computing SHAP on subsample of {len(idx):,} rows")
    explainer = shap.TreeExplainer(booster)
    # xgboost + shap: for multiclass, .shap_values returns (n_classes, n, n_feat)
    # in older shap; newer returns list. Handle both.
    sv = explainer.shap_values(X[idx])
    if isinstance(sv, list):
        sv = np.stack(sv, axis=0)  # (n_classes, n, n_feat)
    else:
        # Newer shap returns (n, n_feat, n_classes); move class axis to front
        if sv.ndim == 3 and sv.shape[-1] == len(CLASS_NAMES):
            sv = np.transpose(sv, (2, 0, 1))
    assert sv.shape == (len(CLASS_NAMES), len(idx), len(FEATURE_COLS)), sv.shape

    # Global mean-|SHAP| per feature (averaged across classes and samples)
    mean_abs = np.abs(sv).mean(axis=(0, 1))  # shape (n_feat,)
    mean_abs_pct = mean_abs / mean_abs.sum()

    # Per-class mean-|SHAP|
    per_class = np.abs(sv).mean(axis=1)  # (n_classes, n_feat)
    per_class_pct = per_class / per_class.sum(axis=1, keepdims=True)

    # Rank agreement with assigned AHP weights
    assigned = np.array([ASSIGNED_WEIGHTS[f] for f in FEATURE_COLS])
    from scipy.stats import spearmanr, pearsonr
    rho_spear = float(spearmanr(mean_abs_pct, assigned).statistic)
    rho_pear = float(pearsonr(mean_abs_pct, assigned).statistic)
    print(f"[shap] Spearman rho(recovered, assigned) = {rho_spear:+.3f}")
    print(f"[shap] Pearson  r  (recovered, assigned) = {rho_pear:+.3f}")

    # Plot: side-by-side bars
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(FEATURE_COLS))
    w = 0.4
    ax.bar(x - w/2, assigned, w, label="Assigned AHP weight", color="#c78d3f")
    ax.bar(x + w/2, mean_abs_pct, w, label="Recovered mean-|SHAP| share", color="#3f7dc7")
    ax.set_xticks(x); ax.set_xticklabels(FEATURE_COLS, rotation=20)
    ax.set_ylabel("Share of total")
    ax.set_title(f"Recovered feature importance vs assigned AHP weight  "
                 f"(Spearman ρ = {rho_spear:+.2f})")
    ax.legend()
    ax.grid(True, alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "08_shap_vs_weights.png", dpi=140)
    plt.close(fig)

    # ---- Report ----
    lines: list[str] = []
    a = lines.append
    a("# 08 — SHAP validation of the constructed target\n")
    a("If the XGBoost model has truly learned SUSCEP_v2 from the seven "
      "conditioning factors, the mean-|SHAP| share it attributes to each "
      "feature should track the AHP weights we used to construct "
      "SUSCEP_v2 in the first place. Any large disagreement would flag "
      "either a bug in the construction, a bug in the model, or that the "
      "model has found a non-obvious interaction we did not account for.\n")

    a("## Feature-importance table")
    a("| Feature | Assigned AHP weight | Recovered mean-|SHAP| share |")
    a("|---|---:|---:|")
    for i, f in enumerate(FEATURE_COLS):
        a(f"| {f} | {assigned[i]:.3f} | {mean_abs_pct[i]:.3f} |")
    a("")
    a(f"- Spearman ρ(recovered, assigned) = **{rho_spear:+.3f}**")
    a(f"- Pearson r(recovered, assigned)  = **{rho_pear:+.3f}**")
    a("")
    a("![shap vs weights](08_shap_vs_weights.png)")
    a("")
    a("## Per-class SHAP shares")
    a("| Feature | " + " | ".join(CLASS_NAMES) + " |")
    a("|---|" + "---:|" * len(CLASS_NAMES))
    for i, f in enumerate(FEATURE_COLS):
        row = " | ".join(f"{per_class_pct[c, i]:.3f}" for c in range(len(CLASS_NAMES)))
        a(f"| {f} | {row} |")
    a("")
    a("The per-class shares show which factors most influence membership "
      "of each risk class. Residents whose home falls in a `High` / "
      "`Very_High` class typically get an explanation that highlights the "
      "top-|SHAP| factors *for their specific point* — see `explain.py`.")

    (REPORTS_DIR / "08_shap_validation.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    # Persist SHAP summary for the export/explanation layer
    np.savez_compressed(
        PROCESSED_DIR / "shap_summary.npz",
        mean_abs=mean_abs, mean_abs_pct=mean_abs_pct,
        per_class=per_class, per_class_pct=per_class_pct,
        feature_cols=np.array(list(FEATURE_COLS)),
        class_names=np.array(list(CLASS_NAMES)),
    )
    print(f"[shap] wrote {REPORTS_DIR / '08_shap_validation.md'}")
    print(f"[shap] wrote {PROCESSED_DIR / 'shap_summary.npz'}")


if __name__ == "__main__":
    main()
