# FloodWarn

A flood-risk classification and decision-support app for Ibadan metropolis. Search or geolocate any area and get an immediate, visual, explained susceptibility rating.

Built as a research + product project: methodology is thesis-grade, delivery is production-grade.

## What's here

```
FloodWarn/
├── ml/                    Python — model training + risk-layer export
├── data/                  raw CSV, processed intermediates, exported layer
├── models/                trained model artefacts (XGBoost, DNN, meta)
├── reports/               methodology, evaluation, SHAP validation
├── db/                    Postgres/PostGIS schema
├── scripts/               loaders + map-tile builder
├── app/                   Next.js web app (deployed to Vercel)
├── DEPLOY.md              Neon + Vercel setup, step by step
└── README.md              this file
```

## Methodology, in one paragraph

The dataset's provided `SUSCEP` label turned out to be a univariate quantile binning of the `Drainage` column alone (100.00% spatial leave-one-cluster-out accuracy under a shallow decision tree; Spearman ρ with Drainage = 0.975). We reconstructed the target as `SUSCEP_v2`, a literature-informed AHP weighted overlay of all 7 conditioning factors (TWI 0.22, Slope 0.20, Rainfall 0.18, FA 0.15, Drainage 0.12, Curvature 0.08, Aspect 0.05); trained a stacked model (XGBoost tree branch + small MLP DNN branch + logistic-regression meta-learner); validated under **leave-one-cluster-out spatial CV** with KMeans-clustered LGA proxies. SHAP recovers the assigned weights at Spearman ρ = +0.68.

**Headline numbers (stacked model, SUSCEP_v2):**

| Split | Accuracy | F1 macro |
|---|---:|---:|
| Spatial LOCO (mean of 5 folds) | 93.79% | 93.80% |
| Random 80/20 stratified | 93.73% | 93.72% |
| Gap (random − spatial) | **−0.06%** | −0.08% |

Full write-ups: [reports/00_data_quality_assessment.md](reports/00_data_quality_assessment.md), [reports/04_target_construction.md](reports/04_target_construction.md), [reports/05_model_eval.md](reports/05_model_eval.md), [reports/08_shap_validation.md](reports/08_shap_validation.md).

## Running the app locally

```bash
cd app
cp .env.local.example .env.local   # then edit — set DATABASE_URL
npm install
npm run dev
```

Without a `DATABASE_URL`, the `/api/geocode` endpoint and every page still work; `/api/risk` returns 500 with a helpful error message. Follow [DEPLOY.md](DEPLOY.md) for the full Neon setup.

## Retraining

```bash
cd ml
python 01_profile.py             # profile & sentinel audit
python 02_splits.py              # LGA-proxy clusters + splits
python 04_data_quality.py        # methodology diagnostics
python 05_construct_target.py    # SUSCEP_v2
python 06_train_tree_v2.py       # tree branch
python 07_train_dnn_v2.py        # DNN branch
python 08_stack_and_eval.py      # stacking + eval
python 09_shap_explain.py        # SHAP validation
python 10_export_risk_layer.py   # export risk_layer.csv + geojson
```

## What FloodWarn is not

- Not a real-time forecast — it's a susceptibility model.
- Not a substitute for professional flood-risk assessment for property purchase, insurance, or engineering decisions.
- Coverage limited to the five LGAs of Ibadan metropolis.

## Licence

Research/thesis project. Contact the author before any commercial reuse.
