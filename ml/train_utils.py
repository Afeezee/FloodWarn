"""
train_utils.py — Shared helpers for tree and DNN training runs.

Centralises: loading persisted splits, computing sample weights for class
imbalance, and a compact metric bundle used across all model reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np
from sklearn.metrics import (
    accuracy_score, f1_score, confusion_matrix, classification_report,
)
from sklearn.utils.class_weight import compute_sample_weight

from preprocess import CLASS_NAMES


ROOT = Path(__file__).resolve().parent.parent
SPLITS_PATH = ROOT / "data" / "processed" / "splits.npz"


def load_splits() -> dict:
    z = np.load(SPLITS_PATH)
    return {
        "clusters": z["clusters"],
        "random_train_idx": z["random_train_idx"],
        "random_test_idx": z["random_test_idx"],
        "n_clusters": int(z["n_clusters"]),
        "random_seed": int(z["random_seed"]),
    }


def spatial_folds(clusters: np.ndarray) -> Iterator[tuple[int, np.ndarray, np.ndarray]]:
    """Yield (fold_id, train_idx, test_idx) for each cluster held out."""
    for k in range(int(clusters.max()) + 1):
        test = np.where(clusters == k)[0]
        train = np.where(clusters != k)[0]
        yield k, train, test


def sample_weights(y: np.ndarray) -> np.ndarray:
    """Balanced sample weights so class imbalance doesn't skew training."""
    return compute_sample_weight(class_weight="balanced", y=y)


def metric_bundle(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "confusion": confusion_matrix(
            y_true, y_pred, labels=list(range(len(CLASS_NAMES)))
        ).tolist(),
        "report": classification_report(
            y_true, y_pred,
            labels=list(range(len(CLASS_NAMES))),
            target_names=list(CLASS_NAMES),
            zero_division=0,
            output_dict=True,
        ),
    }
