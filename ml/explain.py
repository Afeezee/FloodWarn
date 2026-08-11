"""
explain.py — Plain-language explanation generator, called both by
10_export_risk_layer.py (once, per grid point, at export time) and by
the Next.js API layer via a precomputed field.

Design constraint from the brief: "input: feature values for one point;
output: 2-3 short sentences plus a ranked list of top factors."

Sentences are non-alarmist and factual. Copy is tuned for a resident
audience, not a GIS technician.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from preprocess import CLASS_NAMES, FEATURE_COLS


# Human-readable factor names + short phrasings of what an above/below
# average value means for flood risk. Direction matches the AHP
# construction in 05_construct_target.py.
FACTOR_MEANING = {
    "TWI":       ("Topographic wetness",
                  "sits in a natural water-collecting depression",
                  "sits on well-drained higher ground"),
    "Slope":     ("Slope",
                  "is on relatively flat terrain that drains slowly",
                  "is on steeper terrain that sheds water quickly"),
    "Rainfall":  ("Rainfall intensity",
                  "receives heavier average rainfall than the surrounding area",
                  "receives lighter average rainfall than the surrounding area"),
    "FA":        ("Upstream flow accumulation",
                  "lies downstream of a large water-collecting area",
                  "has little upstream area feeding into it"),
    "Drainage":  ("Drainage density",
                  "has a sparser drainage network to carry water away",
                  "has a dense drainage network that sheds water efficiently"),
    "Curvature": ("Surface curvature",
                  "sits in a concave shape where water pools",
                  "sits on a convex shape where water disperses"),
    "Aspect":    ("Slope aspect",
                  "faces a direction associated with slightly higher runoff",
                  "faces a direction with slightly lower runoff"),
}


@dataclass(frozen=True)
class Explanation:
    sentences: str
    top_factors: list[dict]

    def to_dict(self) -> dict:
        return {"sentences": self.sentences, "top_factors": self.top_factors}


def _direction_phrase(feature: str, value: float, mean: float, std: float) -> tuple[str, float]:
    """Return (phrase, standardised deviation) for a feature's current value.

    Positive z means "in the risk-increasing direction" AFTER accounting
    for the direction inversions declared for construct_target.
    Wraps the FACTOR_MEANING tuple.
    """
    z = (value - mean) / std if std > 1e-9 else 0.0
    # Slope, Drainage, Curvature are protective when high (see AHP), so
    # "risk-positive" means z < 0.
    risk_positive_when_high = feature not in {"Slope", "Drainage", "Curvature"}
    if risk_positive_when_high:
        risk_side = "above" if z > 0 else "below"
        phrase = FACTOR_MEANING[feature][1] if z > 0 else FACTOR_MEANING[feature][2]
    else:
        risk_side = "above" if z < 0 else "below"
        phrase = FACTOR_MEANING[feature][1] if z < 0 else FACTOR_MEANING[feature][2]
    return phrase, abs(z)


def explain_point(
    features: dict,               # {feature_name: value}
    shap_values: dict,            # {feature_name: signed SHAP contribution to the predicted class}
    predicted_class: str,
    class_probability: float,
    feature_means: dict,          # global training means, for direction hints
    feature_stds: dict,           # global training stds
    top_n: int = 3,
) -> Explanation:
    """Compose 2-3 sentences plus a ranked list of top-N drivers."""
    # Rank features by absolute SHAP magnitude
    ranked: list[tuple[str, float]] = sorted(
        ((f, abs(shap_values.get(f, 0.0))) for f in FEATURE_COLS),
        key=lambda t: -t[1],
    )
    top = ranked[:top_n]

    top_records = []
    phrases = []
    for f, contrib in top:
        phrase, z = _direction_phrase(f, features[f], feature_means[f], feature_stds[f])
        top_records.append({
            "feature": f,
            "human_name": FACTOR_MEANING[f][0],
            "value": float(features[f]),
            "shap": float(shap_values.get(f, 0.0)),
            "z": float(z),
            "phrase": phrase,
        })
        phrases.append(phrase)

    # Compose 2-3 sentences. Deliberately calm, avoids alarm language.
    class_phrase = {
        "No_Flood": "very low flood susceptibility",
        "Low": "low flood susceptibility",
        "Moderate": "moderate flood susceptibility",
        "High": "high flood susceptibility",
        "Very_High": "very high flood susceptibility",
    }[predicted_class]

    joiner = _list_join([FACTOR_MEANING[f][0].lower() for f, _ in top])
    driver_sentence = f"The main contributing factors are {joiner}."
    context_sentence = (
        f"Specifically, this point {phrases[0]}" +
        (f", and {phrases[1]}" if len(phrases) > 1 else "") +
        (f", and {phrases[2]}" if len(phrases) > 2 else "") + "."
    )
    headline = (f"This location is classified as **{predicted_class.replace('_', ' ')}** "
                f"({class_phrase}, model confidence {class_probability:.0%}).")

    text = f"{headline} {driver_sentence} {context_sentence}"
    return Explanation(sentences=text, top_factors=top_records)


def _list_join(items: Iterable[str]) -> str:
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


if __name__ == "__main__":
    # Smoke test with dummy values
    feats = {"TWI": -2.0, "Slope": 45.0, "Rainfall": 90.0, "FA": 1200.0,
             "Drainage": 210.0, "Curvature": -1e9, "Aspect": 190.0}
    shap = {"TWI": 0.8, "Drainage": 0.6, "Slope": -0.4, "Rainfall": 0.3,
            "FA": 0.1, "Curvature": 0.05, "Aspect": -0.02}
    means = {"TWI": -7.5, "Slope": 45.0, "Rainfall": 75.0, "FA": 500.0,
             "Drainage": 220.0, "Curvature": 0.0, "Aspect": 180.0}
    stds = {"TWI": 3.0, "Slope": 15.0, "Rainfall": 9.0, "FA": 800.0,
            "Drainage": 7.0, "Curvature": 1e9, "Aspect": 90.0}
    exp = explain_point(feats, shap, "High", 0.71, means, stds)
    print(exp.sentences)
    for tf in exp.top_factors:
        print("  -", tf)
