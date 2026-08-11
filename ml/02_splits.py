"""
02_splits.py — Build both split regimes and persist fold assignments.

Two regimes:
  1. Spatial leave-one-cluster-out. KMeans(k=5) on (lon, lat) to approximate
     the 5 Ibadan LGAs (dataset has no explicit LGA column). Each of the 5
     folds holds one cluster out for test; the remaining 4 form the train set.
  2. Stratified random 80/20 split (single split), stratified on the
     ordinal-encoded SUSCEP target.

Persisted to data/processed/splits.npz so training scripts can reproduce
the exact same folds without re-clustering.

Also writes reports/02_splits.md with a summary table + a PNG of the
cluster map so the "these look like plausible LGAs" argument is documented.

Run:
    python ml/02_splits.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split

from preprocess import load_prepared, CLASS_NAMES


ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

N_CLUSTERS = 5
RANDOM_SEED = 42
TEST_FRAC = 0.20


def build_clusters(coords: pd.DataFrame) -> np.ndarray:
    """KMeans on (lon, lat) -> integer cluster id per row."""
    km = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_SEED, n_init=10)
    return km.fit_predict(coords.values)


def summarise_clusters(coords: pd.DataFrame, y: np.ndarray,
                       clusters: np.ndarray) -> pd.DataFrame:
    """Per-cluster: size, centroid, class distribution."""
    rows = []
    for k in range(N_CLUSTERS):
        mask = clusters == k
        row = {
            "cluster": k,
            "n": int(mask.sum()),
            "pct": float(mask.mean()),
            "centroid_lon": float(coords.loc[mask, "X"].mean()),
            "centroid_lat": float(coords.loc[mask, "Y"].mean()),
        }
        for i, cls in enumerate(CLASS_NAMES):
            row[cls] = int(((y == i) & mask).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def plot_clusters(coords: pd.DataFrame, clusters: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 7))
    scatter = ax.scatter(
        coords["X"].values,
        coords["Y"].values,
        c=clusters,
        cmap="tab10",
        s=1.5,
        alpha=0.6,
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Approximated LGA clusters (KMeans, k=5)")
    ax.set_aspect("equal", adjustable="datalim")
    legend_handles, _ = scatter.legend_elements(prop="colors", alpha=0.8)
    ax.legend(legend_handles, [f"Cluster {i}" for i in range(N_CLUSTERS)],
              title="LGA proxy", loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def build_random_split(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    idx = np.arange(len(y))
    tr, te = train_test_split(
        idx, test_size=TEST_FRAC, random_state=RANDOM_SEED, stratify=y
    )
    return tr, te


def main() -> None:
    _, y, coords = load_prepared()
    print(f"[splits] loaded coords={coords.shape} y={y.shape}")

    clusters = build_clusters(coords)
    cluster_summary = summarise_clusters(coords, y, clusters)
    print("[splits] cluster summary:")
    print(cluster_summary.to_string(index=False))

    rand_tr, rand_te = build_random_split(y)
    print(f"[splits] random split: train={len(rand_tr):,} test={len(rand_te):,}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    splits_path = PROCESSED_DIR / "splits.npz"
    np.savez_compressed(
        splits_path,
        clusters=clusters,
        random_train_idx=rand_tr,
        random_test_idx=rand_te,
        n_clusters=np.int32(N_CLUSTERS),
        random_seed=np.int32(RANDOM_SEED),
        test_frac=np.float32(TEST_FRAC),
    )
    print(f"[splits] wrote {splits_path}")

    plot_path = REPORTS_DIR / "02_clusters.png"
    plot_clusters(coords, clusters, plot_path)
    print(f"[splits] wrote {plot_path}")

    # Report
    lines: list[str] = []
    a = lines.append
    a("# 02 — Split strategy\n")
    a("## Spatial leave-one-cluster-out")
    a(f"- KMeans(k={N_CLUSTERS}) on raw (lon, lat), seed={RANDOM_SEED}. "
      "Approximates the 5 LGAs of Ibadan metropolis since the dataset lacks "
      "an explicit LGA column. Under this regime we run 5 folds; each fold "
      "holds one cluster out as the test set.")
    a("")
    a("### Cluster composition")
    a("| cluster | n | share | centroid (lon, lat) | " +
      " | ".join(CLASS_NAMES) + " |")
    a("|---:|---:|---:|---|" + "---:|" * len(CLASS_NAMES))
    for _, r in cluster_summary.iterrows():
        counts = " | ".join(f"{int(r[c]):,}" for c in CLASS_NAMES)
        a(f"| {int(r['cluster'])} | {int(r['n']):,} | {r['pct']:.1%} | "
          f"({r['centroid_lon']:.4f}, {r['centroid_lat']:.4f}) | {counts} |")
    a("")
    a("Cluster map: ![clusters](02_clusters.png)")
    a("")
    a("## Random stratified 80/20")
    a(f"- Simple `train_test_split(test_size={TEST_FRAC}, stratify=y, "
      f"random_state={RANDOM_SEED})`. Class balance is preserved by "
      "construction. Used *only* for the accuracy-gap comparison against "
      "the spatial regime — not as the primary evaluation.")
    a(f"- Train n={len(rand_tr):,}, Test n={len(rand_te):,}")
    a("")
    a("## Why report both")
    a("A random split lets each cluster contribute rows to both train and "
      "test, so the model can memorise local geography. The spatial split "
      "asks the harder question the app actually faces: *given a hydro-"
      "topographic profile from an unseen area, can we still classify risk?* "
      "The gap between the two scores is the single most honest number in "
      "the eval and will be reported prominently in the thesis.")

    report_path = REPORTS_DIR / "02_splits.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[splits] wrote {report_path}")


if __name__ == "__main__":
    main()
