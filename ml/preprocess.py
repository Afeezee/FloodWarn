"""
preprocess.py — Reusable preprocessing pipeline for the FloodWarn dataset.

Public API:
    load_raw()               -> pandas.DataFrame with normalised headers
    clean_sentinels(df)      -> df with GDAL NoData replaced by NaN
    make_preprocessor()      -> sklearn Pipeline (Imputer + StandardScaler)
    encode_target(y)         -> np.ndarray of int 0..4 (ordinal)
    decode_target(y)         -> np.ndarray of class-name strings
    FEATURE_COLS             -> tuple of feature column names
    CLASS_NAMES              -> tuple of ordered class names

Design notes:
    - X and Y (lon/lat) are held out of the feature set. Under leave-one-LGA-out
      validation, held-out coordinates are unseen and a model that memorises
      geography would score artificially well on the random split and
      collapse on the spatial split. Keeping the feature set purely
      hydro-topographic makes the two splits directly comparable.
    - Sentinel threshold -1e30 matches ml/01_profile.py.
    - Imputation strategy: median. Rationale documented in
      reports/01_data_profile.md (Decision 1).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "Ibadan_Metropolis_Flood_Dataset.csv"

# Ordered so index == ordinal encoding.
CLASS_NAMES: tuple[str, ...] = (
    "No_Flood", "Low", "Moderate", "High", "Very_High",
)
CLASS_TO_INT = {c: i for i, c in enumerate(CLASS_NAMES)}
INT_TO_CLASS = {i: c for c, i in CLASS_TO_INT.items()}

# Feature set fed to the model. X/Y intentionally excluded — see module docstring.
FEATURE_COLS: tuple[str, ...] = (
    "Slope", "Curvature", "Aspect", "TWI", "FA", "Drainage", "Rainfall",
)
COORD_COLS: tuple[str, ...] = ("X", "Y")
TARGET_COL = "SUSCEP"

SENTINEL_THRESHOLD = -1e30
SENTINEL_COLS: tuple[str, ...] = ("Slope", "Curvature", "Aspect", "TWI", "FA")


def load_raw() -> pd.DataFrame:
    """Load raw CSV with header normalisation (strips trailing space on `Curvature`)."""
    df = pd.read_csv(RAW_CSV)
    df.columns = [c.strip() for c in df.columns]
    return df


def clean_sentinels(df: pd.DataFrame) -> pd.DataFrame:
    """Replace GDAL/ArcGIS NoData sentinels (values <= -1e30) with NaN.

    Non-mutating: returns a copy.
    """
    out = df.copy()
    for c in SENTINEL_COLS:
        if c in out.columns:
            out.loc[out[c] <= SENTINEL_THRESHOLD, c] = np.nan
    return out


def make_preprocessor() -> Pipeline:
    """Fit-once, transform-many pipeline: median impute -> standardise.

    Fit on training features (7 columns in FEATURE_COLS), then reuse
    identically for validation, test, and inference at serve time.
    """
    return Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )


def encode_target(y: pd.Series | np.ndarray) -> np.ndarray:
    """Ordinal encoding: No_Flood=0 ... Very_High=4."""
    s = pd.Series(y)
    unknown = set(s.dropna().unique()) - set(CLASS_NAMES)
    if unknown:
        raise ValueError(f"Unknown SUSCEP labels: {sorted(unknown)}")
    return s.map(CLASS_TO_INT).astype("int64").to_numpy()


def decode_target(y: np.ndarray) -> np.ndarray:
    """Inverse of encode_target."""
    return np.array([INT_TO_CLASS[int(v)] for v in y], dtype=object)


def load_prepared() -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """Convenience one-shot loader used by training scripts.

    Returns:
        X_df : DataFrame of features (FEATURE_COLS, sentinels replaced with NaN,
               NOT yet imputed/scaled — the pipeline handles that per fold).
        y    : ordinal-encoded target, int64 array shape (N,)
        coords: DataFrame with X, Y for spatial splitting and mapping.
    """
    df = clean_sentinels(load_raw())
    X_df = df[list(FEATURE_COLS)].reset_index(drop=True)
    y = encode_target(df[TARGET_COL])
    coords = df[list(COORD_COLS)].reset_index(drop=True)
    return X_df, y, coords


if __name__ == "__main__":
    # Smoke test + fit + persist a fitted preprocessor on the full dataset,
    # which is what serve-time inference will use.
    import joblib

    X_df, y, coords = load_prepared()
    print(f"[preprocess] X {X_df.shape}, y {y.shape}, coords {coords.shape}")
    print(f"[preprocess] NaN counts per feature after sentinel cleaning:")
    for c in FEATURE_COLS:
        print(f"  {c:>10}: {int(X_df[c].isna().sum())}")

    pre = make_preprocessor()
    Xt = pre.fit_transform(X_df.values)
    print(f"[preprocess] transformed shape: {Xt.shape}")
    print(f"[preprocess] transformed feature means (should be ~0): "
          f"{np.round(Xt.mean(axis=0), 4)}")
    print(f"[preprocess] transformed feature stds  (should be ~1): "
          f"{np.round(Xt.std(axis=0), 4)}")

    out_path = ROOT / "models" / "preprocess_fullfit.joblib"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"pipeline": pre, "feature_cols": list(FEATURE_COLS),
         "class_names": list(CLASS_NAMES)},
        out_path,
    )
    print(f"[preprocess] saved {out_path}")
