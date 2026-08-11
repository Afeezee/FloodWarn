"""
dnn.py — MLP architecture used by the DNN branch. Importable from
training script and from the export/serve path without the
`importlib.import_module("07_train_dnn_v2")` awkwardness caused by the
digit-prefixed filename convention we use for the training scripts.
"""

from __future__ import annotations

import torch.nn as nn


HIDDEN = (64, 32)
DROPOUT = 0.15


class MLP(nn.Module):
    def __init__(self, in_dim: int, hidden=HIDDEN, dropout=DROPOUT, n_classes: int = 5):
        super().__init__()
        layers = []
        prev = in_dim
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h),
                       nn.ReLU(inplace=True), nn.Dropout(dropout)]
            prev = h
        layers += [nn.Linear(prev, n_classes)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)
