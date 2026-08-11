# Deploying FloodWarn

The full pipeline is: **train once locally → load Neon → deploy Next
app to Vercel**. This document lists each step, the commands to run,
and the settings to configure.

## 1. Neon Postgres (5 minutes)

1. Sign in at [neon.tech](https://neon.tech) → **Create Project** → any
   region close to your users. Pick a database name (e.g. `floodwarn`).
2. In the project's **Connection Details** panel, copy the **pooled**
   connection string. It looks like:
   ```
   postgresql://<user>:<password>@ep-xxx-pooler.<region>.neon.tech/floodwarn?sslmode=require
   ```
3. Enable PostGIS on the database:
   ```bash
   psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
   ```
4. Apply the schema:
   ```bash
   psql "$DATABASE_URL" -f db/schema.sql
   ```
5. **Regenerate the precomputed risk layer** if it's not on disk (the
   167 MB CSV + 197 MB GeoJSON are gitignored — over GitHub's per-file
   limit). This runs the full pipeline; skip if you already have
   `data/processed/risk_layer.csv`:
   ```bash
   cd ml
   python 01_profile.py 02_splits.py 04_data_quality.py \
          05_construct_target.py 06_train_tree_v2.py \
          07_train_dnn_v2.py 08_stack_and_eval.py \
          09_shap_explain.py 10_export_risk_layer.py
   cd .. && python scripts/make_map_layer.py
   ```
6. Load the risk layer into Neon (~20 min through the HTTPS driver,
   resumable + retries transient network drops):
   ```bash
   cd app
   # Ensure app/.env.local has DATABASE_URL set
   node load_neon.mjs
   ```
7. `load_neon.mjs` prints the row count + a couple of nearest-point
   spot-checks at the end. Expected: `row count: 144,401` with five
   ~28k-row classes.

## 2. Vercel (5 minutes)

1. Push the `app/` directory to a new Git repository (GitHub / GitLab).
2. At [vercel.com/new](https://vercel.com/new), **Import Project** and
   point it at the repo. Set **Root Directory** to `app` if the repo
   root contains `app/` alongside `ml/`, `db/`, etc.
3. Under **Environment Variables**, add:
   | Key            | Value                                            | Environments |
   |----------------|--------------------------------------------------|--------------|
   | `DATABASE_URL` | the Neon pooled connection string from step 1    | Production, Preview, Development |
4. Click **Deploy**. First build ~2 minutes.

## 3. Post-deploy smoke test

Against your deployed URL:

```bash
# Static endpoint — should work immediately
curl "https://<your-domain>/api/geocode?q=bodija"

# Dynamic endpoint — requires DATABASE_URL wired up
curl "https://<your-domain>/api/risk?lat=7.4416&lng=3.9012"
# Expected: coverage_ok:true, class:"…", full explanation
```

## 4. When you retrain the model

The precomputed risk layer is the boundary between the ML pipeline and
the app. If you retrain (change the target, hyperparameters, or the
dataset):

```bash
# 1. Regenerate the layer + the map overlay
python ml/06_train_tree_v2.py
python ml/07_train_dnn_v2.py
python ml/08_stack_and_eval.py
python ml/09_shap_explain.py
python ml/10_export_risk_layer.py
python scripts/make_map_layer.py

# 2. Reload the DB (loader TRUNCATEs first, so no cleanup needed)
python scripts/load_risk_layer.py

# 3. Redeploy the app (or wait for the next Git push — Vercel builds on push)
```

## Optional future upgrades

- **Real PMTiles delivery.** `scripts/make_map_layer.py` currently emits
  gzipped GeoJSON (~534 KB). If you install `tippecanoe` (Docker on
  Windows, `brew` on macOS, `apt` on Ubuntu), swap in a tippecanoe →
  PMTiles pipeline and change one URL in `src/app/map/page.tsx`. The
  `pmtiles` npm package is already installed.
- **Analytics.** Vercel Analytics is one flag under Project Settings →
  Analytics.
- **Custom domain.** Project Settings → Domains.
