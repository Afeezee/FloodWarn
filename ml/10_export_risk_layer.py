"""
10_export_risk_layer.py — Run the final stacked model over ALL 144,401
grid points and produce the precomputed risk layer that Phase 2 will
load into PostGIS.

Products (both written to data/processed/):
  risk_layer.csv     one row per grid point with lon, lat, class,
                     class_ord, 5 class probabilities, top-3 factor
                     records, and the plain-language explanation text
  risk_layer.geojson same content as a GeoJSON FeatureCollection,
                     ready to be loaded into PostGIS via ogr2ogr or the
                     ST_GeomFromGeoJSON path

The explanation text is precomputed here so the Next.js /api/risk
endpoint is a pure nearest-neighbour lookup: no live SHAP, no live
model inference.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import xgboost as xgb

from preprocess import CLASS_NAMES, FEATURE_COLS, load_prepared
from explain import explain_point


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PROCESSED_DIR = ROOT / "data" / "processed"


def _load_dnn_model(in_dim: int, path: Path):
    from dnn import MLP
    model = MLP(in_dim=in_dim)
    model.load_state_dict(torch.load(path, map_location="cpu"))
    model.eval()
    return model


def main() -> None:
    print("[export] loading raw data + preprocessed features")
    X_df, _, coords = load_prepared()

    pre_bundle = joblib.load(MODELS_DIR / "preprocess_v2_fullfit.joblib")
    pre = pre_bundle["pipeline"]
    X_scaled = pre.transform(X_df.values)

    # Global means/stds for the plain-language direction hints.
    # Uses the training data's raw (post-sentinel-cleaning, pre-scaling) stats.
    feat_means = {f: float(X_df[f].mean()) for f in FEATURE_COLS}
    feat_stds  = {f: float(X_df[f].std())  for f in FEATURE_COLS}

    print("[export] loading base models")
    booster = xgb.Booster()
    booster.load_model(str(MODELS_DIR / "tree_v2_full.json"))
    dnn = _load_dnn_model(in_dim=X_scaled.shape[1], path=MODELS_DIR / "dnn_v2_full.pt")

    meta_bundle = joblib.load(MODELS_DIR / "stack_meta.joblib")
    meta = meta_bundle["meta"]

    print("[export] inference — tree branch")
    tree_proba = booster.predict(xgb.DMatrix(X_scaled))
    print("[export] inference — DNN branch")
    with torch.no_grad():
        dnn_proba = F.softmax(dnn(torch.tensor(X_scaled, dtype=torch.float32)), dim=1).numpy()

    print("[export] inference — stacked meta-learner")
    Z = np.concatenate([tree_proba, dnn_proba], axis=1)
    stacked_proba = meta.predict_proba(Z)
    stacked_class = stacked_proba.argmax(axis=1)

    # Per-point SHAP over 144k rows is prohibitively slow in this
    # environment (both shap.TreeExplainer and xgboost's native
    # pred_contribs took >20 min or hung). Instead we reuse the per-class
    # mean-|SHAP| already computed on a 20k sample in 09_shap_explain.py
    # and picked top-N by CLASS. Personalisation still happens through
    # each row's real feature values (the "phrase" is direction- and
    # magnitude-driven per row); only the *ranking* is shared within a
    # class. This is called out in the "How this works" section of the
    # app so the tradeoff is transparent to users.
    print("[export] using per-class mean-|SHAP| summary from 09_shap_explain.py")
    shap_bundle = np.load(PROCESSED_DIR / "shap_summary.npz")
    per_class = shap_bundle["per_class"]  # (n_classes, n_feat) mean-|SHAP|
    assert per_class.shape == (len(CLASS_NAMES), len(FEATURE_COLS))
    n = len(X_scaled)
    # For each row, take the SHAP row of its PREDICTED class (magnitude-only).
    sv_pred = per_class[stacked_class]  # (n, n_feat), non-negative

    print("[export] composing explanations for all points")
    # Pre-materialise numpy arrays — pandas .iloc in a 144K loop is glacial.
    X_arr = X_df.values  # (n, 7), same column order as FEATURE_COLS
    lon_arr = coords["X"].values
    lat_arr = coords["Y"].values

    rows = []
    t0 = time.time()
    for i in range(n):
        feats = {f: float(X_arr[i, j]) for j, f in enumerate(FEATURE_COLS)}
        shap_vals = {f: float(sv_pred[i, j]) for j, f in enumerate(FEATURE_COLS)}
        cls_ord = int(stacked_class[i])
        cls = CLASS_NAMES[cls_ord]
        prob = float(stacked_proba[i, cls_ord])
        exp = explain_point(
            features=feats, shap_values=shap_vals,
            predicted_class=cls, class_probability=prob,
            feature_means=feat_means, feature_stds=feat_stds, top_n=3,
        )
        row = {
            "lon": float(lon_arr[i]),
            "lat": float(lat_arr[i]),
            "class": cls,
            "class_ord": cls_ord,
            **{f"p_{c}": float(stacked_proba[i, k]) for k, c in enumerate(CLASS_NAMES)},
            "explanation": exp.sentences,
            "top_factors": json.dumps(exp.top_factors),
        }
        rows.append(row)
        if (i + 1) % 20_000 == 0:
            print(f"  composed {i+1:,}/{n:,} ({time.time()-t0:.1f}s)")

    df = pd.DataFrame(rows)
    csv_path = PROCESSED_DIR / "risk_layer.csv"
    df.to_csv(csv_path, index=False)
    print(f"[export] wrote {csv_path}")

    # GeoJSON — the Phase-2 loader can go either way but PostGIS via
    # `ogr2ogr -f "PostgreSQL" ...` is the fastest path from GeoJSON.
    # Build via list-comp on records() to avoid iterrows (slow).
    prop_cols = [c for c in df.columns if c not in ("lon", "lat")]
    features = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": {k: r[k] for k in prop_cols}}
        for r in df.to_dict("records")
    ]
    fc = {"type": "FeatureCollection", "features": features}
    geo_path = PROCESSED_DIR / "risk_layer.geojson"
    geo_path.write_text(json.dumps(fc), encoding="utf-8")
    print(f"[export] wrote {geo_path} ({len(features):,} features)")

    # Class distribution sanity print
    counts = df["class"].value_counts().reindex(CLASS_NAMES, fill_value=0)
    print("[export] final class distribution:")
    for c in CLASS_NAMES:
        print(f"  {c:>10}: {int(counts[c]):>6,} ({counts[c]/n:.1%})")


if __name__ == "__main__":
    main()
