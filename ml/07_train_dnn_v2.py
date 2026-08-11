"""
07_train_dnn_v2.py — Train the DNN branch on SUSCEP_v2 under both split
regimes and produce OOF probabilities used later by the stacked
meta-learner.

Small MLP by design: 7-dim input, three hidden blocks with BatchNorm +
Dropout, softmax over 5 classes. Kept small so it can train on CPU in
reasonable wall-clock time and so its bias/variance profile is different
from the tree branch (which is what stacking needs).

Outputs:
    models/dnn_v2_spatial_fold{k}.pt         per-fold state dicts
    models/dnn_v2_random.pt                  random-split state dict
    models/dnn_v2_full.pt                    all-data state dict for serve-time
    data/processed/dnn_v2_oof_spatial.npz    OOF probs + preds + fold ids + y
    data/processed/dnn_v2_random_preds.npz   random-split predictions
    reports/07_dnn_v2.json                   metrics under both regimes
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from preprocess import CLASS_NAMES, FEATURE_COLS, load_prepared, make_preprocessor
from train_utils import load_splits, spatial_folds, sample_weights, metric_bundle
from dnn import MLP as _SharedMLP, HIDDEN as _SHARED_HIDDEN, DROPOUT as _SHARED_DROPOUT


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

N_CLASSES = len(CLASS_NAMES)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Arch is defined in dnn.py so the export/serve path can rebuild the
# same network to load our state dicts.
HIDDEN = _SHARED_HIDDEN
DROPOUT = _SHARED_DROPOUT
LR = 5e-3
BATCH = 16384                 # larger batch, fewer optim steps per epoch
EPOCHS = 15                   # capped — CPU-only training budget
PATIENCE = 3
MLP = _SharedMLP


def _class_weight_tensor(y_tr: np.ndarray) -> torch.Tensor:
    from sklearn.utils.class_weight import compute_class_weight
    w = compute_class_weight("balanced", classes=np.arange(N_CLASSES), y=y_tr)
    return torch.tensor(w, dtype=torch.float32, device=DEVICE)


def _train_one(X_tr, y_tr, X_te, y_te, tag: str) -> tuple[MLP, np.ndarray, int]:
    """Train one MLP on (X_tr, y_tr), evaluated on (X_te, y_te).
    Returns fitted model, softmax probabilities for X_te, best epoch."""
    Xt_tr = torch.tensor(X_tr, dtype=torch.float32)
    yt_tr = torch.tensor(y_tr, dtype=torch.long)
    Xt_te = torch.tensor(X_te, dtype=torch.float32).to(DEVICE)
    yt_te = torch.tensor(y_te, dtype=torch.long).to(DEVICE)

    dl = DataLoader(TensorDataset(Xt_tr, yt_tr), batch_size=BATCH,
                    shuffle=True, drop_last=False, num_workers=0)

    model = MLP(in_dim=X_tr.shape[1]).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min",
                                                       patience=2, factor=0.5)
    cls_w = _class_weight_tensor(y_tr)
    loss_fn = nn.CrossEntropyLoss(weight=cls_w)

    best_val = float("inf"); best_epoch = 0; best_state = None; bad = 0
    for epoch in range(1, EPOCHS + 1):
        model.train()
        for xb, yb in dl:
            xb = xb.to(DEVICE); yb = yb.to(DEVICE)
            opt.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(Xt_te)
            val_loss = loss_fn(val_logits, yt_te).item()
        sched.step(val_loss)

        if val_loss < best_val - 1e-4:
            best_val = val_loss; best_epoch = epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
            if bad >= PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        proba = F.softmax(model(Xt_te), dim=1).cpu().numpy()
    return model, proba, best_epoch


def main() -> None:
    for d in (MODELS_DIR, PROCESSED_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    print(f"[dnn_v2] device: {DEVICE}")
    torch.manual_seed(42); np.random.seed(42)

    X_df, _, _ = load_prepared()
    X = X_df.values
    y = np.load(PROCESSED_DIR / "susceptibility_v2.npz")["class_v2"].astype(np.int64)
    splits = load_splits()

    results = {"features": list(FEATURE_COLS), "target": "SUSCEP_v2",
               "arch": {"hidden": list(HIDDEN), "dropout": DROPOUT},
               "opt": {"lr": LR, "batch": BATCH, "epochs": EPOCHS,
                       "patience": PATIENCE}}

    # ---- Spatial LOCO ----
    print("[dnn_v2] SPATIAL leave-one-cluster-out")
    fold_metrics = []
    oof_proba = np.zeros((len(y), N_CLASSES), dtype=np.float32)
    oof_pred = np.full(len(y), -1, dtype=np.int64)
    oof_fold = np.full(len(y), -1, dtype=np.int64)

    t0 = time.time()
    for fold, tr, te in spatial_folds(splits["clusters"]):
        pre = make_preprocessor()
        X_tr = pre.fit_transform(X[tr]); X_te = pre.transform(X[te])
        model, proba, best_epoch = _train_one(X_tr, y[tr], X_te, y[te], tag=f"spatial_f{fold}")
        pred = proba.argmax(axis=1)
        m = metric_bundle(y[te], pred); m["fold"] = fold; m["n_test"] = int(len(te))
        m["best_epoch"] = int(best_epoch)
        fold_metrics.append(m)
        print(f"  fold {fold}: n={len(te):,} acc={m['accuracy']:.4f} "
              f"f1_macro={m['f1_macro']:.4f} best_epoch={best_epoch}")
        oof_proba[te] = proba.astype(np.float32)
        oof_pred[te] = pred; oof_fold[te] = fold
        torch.save(model.state_dict(), MODELS_DIR / f"dnn_v2_spatial_fold{fold}.pt")

    spatial_overall = metric_bundle(y, oof_pred)
    print(f"  OVERALL spatial (OOF): acc={spatial_overall['accuracy']:.4f} "
          f"f1_macro={spatial_overall['f1_macro']:.4f}")
    print(f"[dnn_v2] spatial regime done in {time.time()-t0:.1f}s")

    np.savez_compressed(
        PROCESSED_DIR / "dnn_v2_oof_spatial.npz",
        oof_proba=oof_proba, oof_pred=oof_pred, oof_fold=oof_fold, y=y,
    )
    results["spatial"] = {"per_fold": fold_metrics, "overall_oof": spatial_overall}

    # ---- Random split ----
    print("[dnn_v2] RANDOM stratified 80/20")
    tr = splits["random_train_idx"]; te = splits["random_test_idx"]
    pre = make_preprocessor()
    X_tr = pre.fit_transform(X[tr]); X_te = pre.transform(X[te])
    model, proba, best_epoch = _train_one(X_tr, y[tr], X_te, y[te], tag="random")
    pred = proba.argmax(axis=1)
    random_metrics = metric_bundle(y[te], pred); random_metrics["best_epoch"] = int(best_epoch)
    print(f"  RANDOM: acc={random_metrics['accuracy']:.4f} "
          f"f1_macro={random_metrics['f1_macro']:.4f} best_epoch={best_epoch}")
    torch.save(model.state_dict(), MODELS_DIR / "dnn_v2_random.pt")
    np.savez_compressed(
        PROCESSED_DIR / "dnn_v2_random_preds.npz",
        proba=proba.astype(np.float32), pred=pred, y=y[te], test_idx=te,
    )
    results["random"] = random_metrics

    # ---- Full-data fit ----
    print("[dnn_v2] FULL-data fit")
    pre_full = make_preprocessor()
    X_full = pre_full.fit_transform(X)
    # Use random-split test set as val for early stopping in the full fit,
    # so we still get a valid stopping signal.
    model, _, best_epoch = _train_one(X_full[tr], y[tr], X_full[te], y[te], tag="full")
    # Then retrain on all data for the same # of epochs to keep the
    # model comparable but exposed to every point.
    Xt = torch.tensor(X_full, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.long)
    dl = DataLoader(TensorDataset(Xt, yt), batch_size=BATCH, shuffle=True)
    model_full = MLP(in_dim=X_full.shape[1]).to(DEVICE)
    opt = torch.optim.Adam(model_full.parameters(), lr=LR, weight_decay=1e-5)
    cls_w = _class_weight_tensor(y)
    loss_fn = nn.CrossEntropyLoss(weight=cls_w)
    for epoch in range(1, max(5, best_epoch) + 1):
        model_full.train()
        for xb, yb in dl:
            xb = xb.to(DEVICE); yb = yb.to(DEVICE)
            opt.zero_grad()
            loss_fn(model_full(xb), yb).backward()
            opt.step()
    torch.save(model_full.state_dict(), MODELS_DIR / "dnn_v2_full.pt")
    joblib.dump(
        {"pipeline": pre_full, "feature_cols": list(FEATURE_COLS),
         "class_names": list(CLASS_NAMES), "target": "SUSCEP_v2",
         "arch": {"hidden": list(HIDDEN), "dropout": DROPOUT}},
        MODELS_DIR / "preprocess_dnn_v2_fullfit.joblib",
    )
    print(f"[dnn_v2] full-data fit done ({max(5,best_epoch)} epochs)")

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
    print("[dnn_v2] summary:", json.dumps(results["summary"], indent=2))

    (REPORTS_DIR / "07_dnn_v2.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(f"[dnn_v2] wrote {REPORTS_DIR / '07_dnn_v2.json'}")


if __name__ == "__main__":
    main()
