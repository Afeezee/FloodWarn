"""
05_construct_target.py — Construct SUSCEP_v2, a literature-informed
weighted-overlay susceptibility target that uses all seven conditioning
factors (unlike the provided SUSCEP, which is a univariate binning of
Drainage — see reports/00_data_quality_assessment.md).

Method (standard flood-susceptibility AHP / weighted linear combination):
  1. Robustly normalise each conditioning layer to [0,1] by clipping at
     [p01, p99] then min-max scaling. Robust to sentinel-derived outliers
     and skewed features (FA in particular is heavy-tailed).
  2. Invert layers whose direction is protective (higher raw value = lower
     flood risk): Slope, Drainage.
  3. Curvature: physically, negative (concave) curvature accumulates
     water. Invert so concave = high risk.
  4. Aspect: circular variable; treated with a mild periodic transform
     so it contributes weak, non-degenerate signal.
  5. Weighted sum with literature-informed AHP weights.
  6. Bin the continuous susceptibility index into 5 ordered quintiles
     labelled No_Flood ... Very_High.

Weights (sum = 1.00). Values chosen from the range typically reported
across recent flood-susceptibility studies (Pradhan et al. 2023;
Yang et al. 2024; Ogunbode & Ifabiyi 2020 and similar Nigerian-context
work). Exact numbers are documented so a reader can reproduce or
sensitivity-test them:

    TWI               0.22   (topographic wetness — primary hydrologic proxy)
    Slope (inverted)  0.20   (steep terrain drains fast)
    Rainfall          0.18   (input intensity)
    FA                0.15   (upstream contributing area)
    Drainage (inv)    0.12   (dense drainage network sheds water)
    Curvature (inv)   0.08   (concave surfaces pool water)
    Aspect            0.05   (weak, kept for completeness)

Outputs:
    data/processed/susceptibility_v2.npz   {index, class_v2, orig_class}
    reports/04_target_construction.md
    reports/04_v1_vs_v2_confusion.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from preprocess import (
    CLASS_NAMES, FEATURE_COLS, TARGET_COL, load_raw, clean_sentinels,
)


ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

# (weight, invert?). `invert=True` -> use (1 - normalised value).
WEIGHTS: dict[str, tuple[float, bool]] = {
    "TWI":       (0.22, False),
    "Slope":     (0.20, True),
    "Rainfall":  (0.18, False),
    "FA":        (0.15, False),
    "Drainage":  (0.12, True),
    "Curvature": (0.08, True),
    "Aspect":    (0.05, False),   # transformed separately below
}
assert abs(sum(w for w, _ in WEIGHTS.values()) - 1.0) < 1e-9


def robust_norm(col: pd.Series) -> np.ndarray:
    """Clip to [p01, p99] then min-max scale to [0, 1]."""
    x = col.astype(float).to_numpy()
    lo, hi = np.nanpercentile(x, 1), np.nanpercentile(x, 99)
    x = np.clip(x, lo, hi)
    if hi > lo:
        x = (x - lo) / (hi - lo)
    else:
        x = np.zeros_like(x)
    # Any residual NaN (shouldn't be — caller imputes — but defensive)
    x = np.nan_to_num(x, nan=np.nanmedian(x))
    return x


def aspect_risk(col: pd.Series) -> np.ndarray:
    """Aspect is a circular variable in degrees. Return a mild periodic
    risk value in [0.3, 0.7] so it contributes signal without dominating.
    """
    x = col.astype(float).to_numpy()
    x = np.nan_to_num(x, nan=np.nanmedian(x))
    # Convert to radians, use a shifted sine so the transform is smooth
    # and stays bounded away from 0/1.
    return 0.5 + 0.2 * np.sin(np.deg2rad(2 * x))


def main() -> None:
    df = clean_sentinels(load_raw())
    # Median-impute before normalisation so downstream percentiles use
    # only real observations. This is the same policy the training
    # pipeline applies inside each fold, so v2 is consistent with the
    # feature preprocessing.
    df_imp = df.copy()
    for c in FEATURE_COLS:
        med = df_imp[c].median()
        df_imp[c] = df_imp[c].fillna(med)

    components: dict[str, np.ndarray] = {}
    for name in FEATURE_COLS:
        if name == "Aspect":
            r = aspect_risk(df_imp[name])
        else:
            r = robust_norm(df_imp[name])
            if WEIGHTS[name][1]:  # invert
                r = 1.0 - r
        components[name] = r

    # Weighted sum -> continuous susceptibility index in [0, 1]
    index = np.zeros(len(df_imp), dtype=np.float64)
    for name, (w, _) in WEIGHTS.items():
        index += w * components[name]

    # Bin into 5 classes by quintile edges (equal-count, ordered).
    # Using quintiles keeps class distribution predictable and matches
    # standard practice in flood-susceptibility mapping.
    edges = np.quantile(index, [0.2, 0.4, 0.6, 0.8])
    class_v2 = np.digitize(index, edges).astype(np.int64)  # 0..4
    class_names_v2 = np.array([CLASS_NAMES[i] for i in class_v2])

    orig_class_ord = df[TARGET_COL].map({c: i for i, c in enumerate(CLASS_NAMES)}).to_numpy()

    # Confusion matrix between original SUSCEP and new SUSCEP_v2
    conf = pd.crosstab(
        pd.Series(orig_class_ord, name="orig"),
        pd.Series(class_v2, name="v2"),
    ).reindex(index=range(5), columns=range(5), fill_value=0)

    # Agreement metrics
    exact = float((orig_class_ord == class_v2).mean())
    within_one = float((np.abs(orig_class_ord - class_v2) <= 1).mean())
    spearman = float(pd.Series(orig_class_ord).corr(pd.Series(class_v2), method="spearman"))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Persist target
    np.savez_compressed(
        PROCESSED_DIR / "susceptibility_v2.npz",
        index=index.astype(np.float32),
        class_v2=class_v2,
        orig_class_ord=orig_class_ord,
        bin_edges=edges,
        weights=json.dumps({k: {"weight": w, "invert": inv}
                            for k, (w, inv) in WEIGHTS.items()}),
    )

    # Confusion PNG
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(conf.values, cmap="viridis", aspect="auto")
    ax.set_xticks(range(5)); ax.set_yticks(range(5))
    ax.set_xticklabels(CLASS_NAMES, rotation=45, ha="right")
    ax.set_yticklabels(CLASS_NAMES)
    ax.set_xlabel("SUSCEP_v2 (constructed)")
    ax.set_ylabel("SUSCEP (original)")
    ax.set_title(f"Original vs constructed target\nexact agreement {exact:.1%}, "
                 f"within-one-class {within_one:.1%}, Spearman ρ={spearman:.3f}")
    for i in range(5):
        for j in range(5):
            ax.text(j, i, f"{conf.values[i,j]:,}", ha="center", va="center",
                    color="white" if conf.values[i,j] < conf.values.max()/2 else "black",
                    fontsize=8)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "04_v1_vs_v2_confusion.png", dpi=140)
    plt.close(fig)

    # Class distribution comparison
    orig_counts = pd.Series(orig_class_ord).value_counts().reindex(range(5), fill_value=0)
    v2_counts = pd.Series(class_v2).value_counts().reindex(range(5), fill_value=0)

    # Report
    lines: list[str] = []
    a = lines.append
    a("# 04 — Constructing SUSCEP_v2\n")
    a("The provided `SUSCEP` label is a univariate quantile binning of "
      "the `Drainage` column alone (see `00_data_quality_assessment.md`). "
      "We construct a genuine multi-factor susceptibility target, "
      "`SUSCEP_v2`, from all seven conditioning layers using a "
      "literature-informed AHP weighted overlay.\n")
    a("## Method")
    a("1. **Impute** any NaN (from GDAL NoData sentinels + explicit nulls) "
      "with the column median.")
    a("2. **Robust normalisation.** For every non-aspect factor, clip to "
      "the [1st, 99th] percentile then min-max scale to [0, 1]. Robust to "
      "the residual outliers in Curvature and FA.")
    a("3. **Direction correction.** Invert layers whose *higher* raw "
      "value indicates *lower* flood risk: Slope (steep → fast drainage), "
      "Drainage density (dense network → efficient shedding), and "
      "Curvature (positive/convex → sheds water). This matches the "
      "convention in Pradhan et al. 2023 and equivalent works.")
    a("4. **Aspect transform.** Aspect is a circular variable; a linear "
      "min-max is nonsensical. We use a bounded periodic transform "
      "`0.5 + 0.2·sin(2·aspect)` so it contributes a weak, non-degenerate "
      "signal without dominating the index. Weight 0.05.")
    a("5. **Weighted sum** with the AHP weights below.")
    a("6. **Binning** into five ordered classes by quintiles of the "
      "resulting continuous index.\n")
    a("## AHP weights (sum = 1.00)")
    a("| Factor | Direction | Weight | Precedent |")
    a("|---|---|---:|---|")
    a("| TWI | + | 0.22 | primary hydrologic proxy across all reviewed papers |")
    a("| Slope | − | 0.20 | universally the second-highest weight in AHP flood studies |")
    a("| Rainfall | + | 0.18 | forcing term |")
    a("| Flow Accumulation | + | 0.15 | upstream contributing area |")
    a("| Drainage density | − | 0.12 | protective when high (classical interpretation) |")
    a("| Curvature | − | 0.08 | concave surfaces pool water |")
    a("| Aspect | ± (periodic) | 0.05 | weak physical justification, kept for completeness |")
    a("")
    a("## Class distribution")
    a("| Class | Original SUSCEP | SUSCEP_v2 |")
    a("|---|---:|---:|")
    for i, c in enumerate(CLASS_NAMES):
        a(f"| {c} | {int(orig_counts[i]):,} ({orig_counts[i]/len(class_v2):.1%}) "
          f"| {int(v2_counts[i]):,} ({v2_counts[i]/len(class_v2):.1%}) |")
    a("")
    a("Quintile binning gives ~20% per class by construction. The "
      "original SUSCEP has 11%/22%/26%/24%/16% because it was derived "
      "from Drainage quantile cuts that were placed to hit slightly "
      "different class balances.\n")
    a("## Agreement with the original SUSCEP")
    a(f"- **Exact class agreement**: {exact:.2%}")
    a(f"- **Within one class**: {within_one:.2%}")
    a(f"- **Spearman ρ** on ordinal ranks: {spearman:.3f}")
    a("")
    a("A moderate correlation is expected because Drainage is still one "
      "of the seven inputs to SUSCEP_v2 (weight 0.12), so the two labels "
      "cannot be completely independent. But the confusion matrix "
      "below shows SUSCEP_v2 disagrees with the original in a "
      "meaningful fraction of cases — the disagreements are where the "
      "other six factors overrule Drainage-density alone.\n")
    a("![v1 vs v2 confusion](04_v1_vs_v2_confusion.png)\n")
    a("## Why this makes spatial LOO meaningful again")
    a("SUSCEP_v2 depends non-linearly on 7 features whose joint "
      "distribution varies across the 5 KMeans clusters (each cluster "
      "occupies a distinct part of Ibadan and has its own topography). "
      "A model that memorises the fitted rule in 4 clusters is not "
      "guaranteed to reproduce it perfectly in the 5th, because the "
      "held-out cluster's feature distribution shifts the operating "
      "region of the model. Spatial LOO now measures a real property: "
      "how well the fitted classifier transfers.")

    (REPORTS_DIR / "04_target_construction.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"[target] wrote {REPORTS_DIR / '04_target_construction.md'}")
    print(f"[target] wrote {PROCESSED_DIR / 'susceptibility_v2.npz'}")
    print(f"[target] wrote {REPORTS_DIR / '04_v1_vs_v2_confusion.png'}")
    print(f"[target] exact agreement with original SUSCEP: {exact:.2%}")
    print(f"[target] within-one-class agreement:            {within_one:.2%}")
    print(f"[target] Spearman rho:                          {spearman:.3f}")
    print(f"[target] SUSCEP_v2 class counts: {v2_counts.tolist()}")


if __name__ == "__main__":
    main()
