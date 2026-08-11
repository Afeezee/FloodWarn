"""
01_profile.py — Validate the Ibadan Metropolis Flood Dataset against the
FloodWarn brief's expected schema and characterise every column.

Outputs:
    reports/01_data_profile.md   human-readable profile
    data/processed/profile.json  machine-readable summary (for downstream scripts)

Run:
    python ml/01_profile.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "Ibadan_Metropolis_Flood_Dataset.csv"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

# Expected schema per the FloodWarn build brief.
EXPECTED_COLS = [
    "X", "Y", "Slope", "Curvature", "Aspect",
    "TWI", "FA", "Drainage", "Rainfall", "SUSCEP",
]
EXPECTED_ROWS = 144_401
SUSCEP_CLASSES = ["No_Flood", "Low", "Moderate", "High", "Very_High"]
# Approximate lon/lat bounding box for Ibadan metropolis (5 LGAs), used as
# a sanity check, not a hard reject.
IBADAN_LON = (3.75, 4.10)
IBADAN_LAT = (7.25, 7.55)


def load_and_normalise() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    # Header has "Curvature " with a trailing space in the raw file. Strip.
    df.columns = [c.strip() for c in df.columns]
    return df


def column_stats(series: pd.Series) -> dict:
    s = series.dropna()
    return {
        "dtype": str(series.dtype),
        "n_null": int(series.isna().sum()),
        "pct_null": round(series.isna().mean() * 100, 4),
        "min": float(s.min()) if len(s) else None,
        "max": float(s.max()) if len(s) else None,
        "mean": float(s.mean()) if len(s) else None,
        "median": float(s.median()) if len(s) else None,
        "std": float(s.std()) if len(s) else None,
        "p01": float(np.percentile(s, 1)) if len(s) else None,
        "p99": float(np.percentile(s, 99)) if len(s) else None,
    }


def main() -> None:
    print(f"[profile] loading {RAW_CSV}")
    df = load_and_normalise()

    schema_ok = list(df.columns) == EXPECTED_COLS
    row_delta = len(df) - EXPECTED_ROWS

    # SUSCEP class distribution and label sanity
    susc_counts = df["SUSCEP"].value_counts(dropna=False).to_dict()
    unexpected_labels = sorted(set(df["SUSCEP"].dropna().unique()) - set(SUSCEP_CLASSES))

    # Spatial sanity — do X/Y fall inside the Ibadan bbox?
    lon_in = df["X"].between(*IBADAN_LON).mean()
    lat_in = df["Y"].between(*IBADAN_LAT).mean()

    # Per-column stats
    stats = {c: column_stats(df[c]) for c in df.columns if c != "SUSCEP"}

    # NoData sentinel detection. GDAL/ArcGIS write -FLT_MAX (~ -3.4e38)
    # into rasters for missing pixels; when exported to CSV these come
    # through as literal floats, not NaN. Anything below -1e30 is treated
    # as sentinel here.
    SENTINEL_THRESHOLD = -1e30
    sentinel_cols = ["Slope", "Curvature", "Aspect", "TWI", "FA"]
    sentinel_counts = {
        c: int((df[c] <= SENTINEL_THRESHOLD).sum()) for c in sentinel_cols
    }
    # Rows with sentinel in >=1 of those columns
    sentinel_mask = np.zeros(len(df), dtype=bool)
    for c in sentinel_cols:
        sentinel_mask |= (df[c].values <= SENTINEL_THRESHOLD)
    rows_with_sentinel = int(sentinel_mask.sum())

    # Curvature anomaly — even after sentinels are removed, values are
    # scaled ~1e10 vs. the textbook ±0.1 range. Kept as-is per user
    # direction; StandardScaler will normalise before training.
    curv_clean = df["Curvature"][df["Curvature"] > SENTINEL_THRESHOLD]
    curv_abs_max_clean = float(curv_clean.abs().max())

    # Build report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    a = lines.append
    a("# 01 — Data profile: Ibadan Metropolis Flood Dataset\n")
    a(f"- File: `{RAW_CSV.relative_to(ROOT)}`")
    a(f"- Rows: **{len(df):,}** (expected {EXPECTED_ROWS:,}, delta {row_delta:+})")
    a(f"- Columns: **{len(df.columns)}** (expected {len(EXPECTED_COLS)})")
    a(f"- Schema matches brief: **{'YES' if schema_ok else 'NO'}**")
    a(f"- Header normalisation: stripped trailing space on `Curvature`")
    a("")
    a("## SUSCEP target")
    a(f"- Unexpected labels: {unexpected_labels or 'none'}")
    a("")
    a("| Class | Count | Share |")
    a("|---|---:|---:|")
    total = int(df["SUSCEP"].notna().sum())
    for cls in SUSCEP_CLASSES:
        n = int(susc_counts.get(cls, 0))
        share = n / total if total else 0.0
        a(f"| {cls} | {n:,} | {share:.1%} |")
    a("")
    a("## Spatial sanity (Ibadan bbox check)")
    a(f"- Longitude in [{IBADAN_LON[0]}, {IBADAN_LON[1]}]: **{lon_in:.1%}** of rows")
    a(f"- Latitude in [{IBADAN_LAT[0]}, {IBADAN_LAT[1]}]: **{lat_in:.1%}** of rows")
    a(f"- Actual X (lon) range: [{df['X'].min():.4f}, {df['X'].max():.4f}]")
    a(f"- Actual Y (lat) range: [{df['Y'].min():.4f}, {df['Y'].max():.4f}]")
    a("")
    a("## Continuous feature statistics")
    a("| col | dtype | nulls | min | p01 | median | mean | p99 | max | std |")
    a("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for c, s in stats.items():
        a(f"| {c} | {s['dtype']} | {s['n_null']} ({s['pct_null']}%) | "
          f"{s['min']:.4g} | {s['p01']:.4g} | {s['median']:.4g} | "
          f"{s['mean']:.4g} | {s['p99']:.4g} | {s['max']:.4g} | {s['std']:.4g} |")
    a("")
    a("## NoData sentinel audit")
    a(f"- Threshold: any value <= {SENTINEL_THRESHOLD:.0e} treated as GDAL/ArcGIS NoData (-FLT_MAX).")
    a("")
    a("| column | sentinel rows |")
    a("|---|---:|")
    for c, n in sentinel_counts.items():
        a(f"| {c} | {n:,} |")
    a("")
    a(f"- **Rows with a sentinel in >=1 of those columns: {rows_with_sentinel:,} "
      f"({rows_with_sentinel/len(df):.2%})**")
    a("- Curvature |max| after sentinel removal: "
      f"**{curv_abs_max_clean:.3e}** (still scaled ~1e10 vs. textbook ±0.1; see decision 2 below).")
    a("")
    a("## Decisions (agreed with user, 2026-08-10)")
    slope_nulls = stats["Slope"]["n_null"]
    a(f"1. **Slope explicit nulls ({slope_nulls}) + all NoData sentinels above** "
      "→ median-imputed inside the preprocessing pipeline (Task 3). "
      "Keeps all 144,401 grid points for the precomputed risk layer so every resident "
      "gets a prediction; imputation limitation documented in the eval report.")
    a("")
    a("2. **Curvature scale (~1e10)** — left as-is. StandardScaler in the "
      "preprocessing pipeline neutralises the scale before training; relative "
      "structure is preserved. Flagged here for the thesis write-up.")
    a("")
    a("3. **Class balance** — max/min ratio is well under 3x. Class-weighted loss "
      "used, no resampling required.")

    report_path = REPORTS_DIR / "01_data_profile.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[profile] wrote {report_path}")

    summary = {
        "n_rows": len(df),
        "expected_rows": EXPECTED_ROWS,
        "schema_ok": schema_ok,
        "susc_counts": {k: int(v) for k, v in susc_counts.items()},
        "unexpected_labels": unexpected_labels,
        "lon_range": [float(df["X"].min()), float(df["X"].max())],
        "lat_range": [float(df["Y"].min()), float(df["Y"].max())],
        "lon_in_bbox_pct": float(lon_in),
        "lat_in_bbox_pct": float(lat_in),
        "curvature_abs_max_clean": curv_abs_max_clean,
        "sentinel_threshold": SENTINEL_THRESHOLD,
        "sentinel_counts": sentinel_counts,
        "rows_with_any_sentinel": rows_with_sentinel,
        "column_stats": stats,
    }
    summary_path = PROCESSED_DIR / "profile.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[profile] wrote {summary_path}")

    # Class balance ratio
    class_ns = [susc_counts.get(c, 0) for c in SUSCEP_CLASSES]
    ratio = max(class_ns) / max(min(class_ns), 1)
    print(f"[profile] class balance ratio (max/min): {ratio:.2f}x")

    # Hard fail if schema is wrong — protects downstream scripts.
    if not schema_ok:
        raise SystemExit(f"Schema mismatch: got {list(df.columns)}")


if __name__ == "__main__":
    main()
