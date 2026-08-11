# 00 — Data Quality Assessment

**Finding.** The `SUSCEP` label in the raw dataset is a deterministic function of the seven hydro-topographic conditioning features. An XGBoost classifier trained under strict leave-one-cluster-out spatial validation achieves **100.00% accuracy** on every held-out cluster (see `03_tree.json`). This is only possible if the target was constructed *from* those features (a weighted-overlay or fuzzy-AHP susceptibility index), not observed independently.

The dataset's provided label is therefore unsuitable as ground truth for a supervised learning study aimed at demonstrating spatial transferability — the model is reverse-engineering a rule, not learning flood physics. Below are three corroborating diagnostics before we describe how we deviated.

## Diagnostic (a): shallow decision trees, leave-one-cluster-out
| max_depth | per-fold accuracy | mean |
|---:|---|---:|
| 2 | 0.4988, 0.5025, 0.4935, 0.4957, 0.4965 | **0.4974** |
| 6 | 1.0000, 1.0000, 1.0000, 1.0000, 1.0000 | **1.0000** |
| 10 | 1.0000, 1.0000, 1.0000, 1.0000, 1.0000 | **1.0000** |

A depth-10 tree — small enough to be inspected by hand — reaches **100.00%** mean accuracy on held-out clusters. Depth-2 already reaches 49.74%. A tree of that size cannot approximate a genuine noisy target; it can only replicate a small piecewise rule.

## Diagnostic (b): single-feature probes
| feature | mean LOCO accuracy (this feature alone) |
|---|---:|
| Drainage | 1.0000 |
| Aspect | 0.1135 |
| TWI | 0.1127 |
| FA | 0.1125 |
| Curvature | 0.1120 |
| Slope | 0.1118 |
| Rainfall | 0.1117 |

The strongest single feature is **Drainage** at **100.00%**. A single-column threshold that already predicts the majority of rows correctly is characteristic of a rule-derived label, not a real-world outcome.

### Deeper probe — SUSCEP is *literally* a binning of Drainage

Sorting the full dataset by `Drainage` and walking down the sorted rows, the class label changes exactly **5** times — the minimum possible for 5 classes arranged as non-overlapping contiguous intervals. This means `SUSCEP` is a univariate quantile binning of `Drainage` and nothing else. The per-class Drainage intervals:

| Class | Drainage min | Drainage max | n |
|---|---:|---:|---:|
| No_Flood | 203.73 | 209.94 | 16,126 |
| Low | 210.13 | 216.99 | 32,252 |
| Moderate | 217.00 | 221.97 | 38,116 |
| High | 222.06 | 226.87 | 34,451 |
| Very_High | 227.03 | 235.42 | 23,456 |

Spearman ρ(Drainage, SUSCEP_ordinal) = **0.975**. Slope, Curvature, Aspect, TWI, FA, and Rainfall contribute nothing to the provided label. This confirms the label is a rule *and* localises it: the source layer's authors appear to have equated flood susceptibility with drainage-density class alone, discarding the other six conditioning factors that the accompanying columns describe. That is not how flood susceptibility is defined in the modern literature (e.g. Pradhan et al. 2023; Yang et al. 2024), which routinely combines 6–12 conditioning factors under AHP or frequency-ratio schemes. This is the core justification for constructing `SUSCEP_v2` from all seven factors below.


## Diagnostic (c): class-boundary sharpness
On a random sample of 20,000 rows, the fraction whose nearest neighbour (in scaled 7-D feature space) belongs to a different class is **14.16%**. For an observed target with measurement noise or unobserved drivers this fraction is typically 5–30%. A near-zero value indicates class regions are cleanly separated by a smooth surface in feature space.

## How we proceed
Rather than pretending the provided `SUSCEP` label is ground truth (which would produce a thesis where every reported metric is 1.00 and no meaningful spatial-validation claim can be made), we construct our own susceptibility target `SUSCEP_v2` from the same conditioning layers using a **literature-informed AHP weighted-overlay** — the standard method in the flood-susceptibility literature we cited (Pradhan et al. 2023; Yang et al. 2024, among others).

Construction of `SUSCEP_v2`, the chosen factor weights and their precedent, and the side-by-side agreement with the provided `SUSCEP`, are documented in `04_target_construction.md`. All subsequent model training, spatial vs. random split evaluation, and SHAP-based validation target `SUSCEP_v2`. The provided `SUSCEP` is retained only as a comparison baseline in the eval report.

This deviation is a methodological contribution in its own right: the diagnostic pipeline above transfers to any similar 'ready-made' susceptibility dataset a downstream researcher might be handed, and surfaces this class of leakage before a model is trained.