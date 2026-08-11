# 09 — Phase 2 API verification

The Next.js app has two API endpoints. `/api/geocode` is purely static
(reads `app/src/data/gazetteer.json`) and was verified live on
2026-08-11. `/api/risk` requires the PostGIS database to be loaded; the
runtime path was verified to fail gracefully with a clear, actionable
error when `DATABASE_URL` is absent.

Once you provision Neon and run the loader, `/api/risk` will return
real predictions for every coordinate below. Sample coordinates and
expected class labels are pulled directly from the precomputed layer
(`data/processed/risk_layer.csv`) so you can spot-check that the
end-to-end pipeline serves the same class the model assigned.

## /api/geocode — verified against dev server

Requests actually sent, responses actually returned, `npm run dev` on
`localhost:3000` on 2026-08-11.

```bash
# Exact name match
curl "http://localhost:3000/api/geocode?q=bodija"
# → {"query":"bodija","results":[{"name":"Bodija","aliases":["New Bodija"],
#     "lat":7.4297,"lng":3.9066,"category":"neighbourhood",
#     "lga":"Ibadan North","score":100}]}

# Alias match
curl "http://localhost:3000/api/geocode?q=UI"
# → {"query":"UI","results":[{"name":"University of Ibadan",
#     "aliases":["UI","U.I."],"lat":7.4416,"lng":3.9012,
#     "category":"landmark","lga":"Ibadan North","score":100}]}

# Multi-word + token overlap ranking
curl "http://localhost:3000/api/geocode?q=ring+road"
# → 2 results, Ring Road (100) > Iwo Road (20 via "road" overlap)

# Missing q
curl -o /dev/null -w "%{http_code}\n" "http://localhost:3000/api/geocode"
# → 400
```

## /api/risk — spot-check coordinates once DATABASE_URL is set

Each row below is a coordinate the model actually classified in the
precomputed risk layer. Once the loader has populated PostGIS, hitting
the endpoint with these lat/lng values should return the class listed.

```bash
# No_Flood (expect class="No_Flood", coverage_ok=true, distance_m<50)
curl "http://localhost:3000/api/risk?lat=7.326389&lng=3.880000"

# Low
curl "http://localhost:3000/api/risk?lat=7.353333&lng=3.903611"

# Moderate
curl "http://localhost:3000/api/risk?lat=7.421389&lng=3.892778"

# High
curl "http://localhost:3000/api/risk?lat=7.396389&lng=3.933333"

# Very_High
curl "http://localhost:3000/api/risk?lat=7.333056&lng=3.849167"

# Outside coverage (Lagos, ~200km away — expect coverage_ok=false)
curl "http://localhost:3000/api/risk?lat=6.5&lng=3.4"

# Missing params
curl -o /dev/null -w "%{http_code}\n" "http://localhost:3000/api/risk"
# → 400
```

## Loading the database

```bash
# 1. Provision Neon → capture DATABASE_URL (must include sslmode=require)
export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/floodwarn?sslmode=require"

# 2. Apply schema (creates the table, GiST index, and nearest_risk() function)
psql "$DATABASE_URL" -f db/schema.sql

# 3. Bulk-load (installs psycopg on first run if missing)
pip install "psycopg[binary]"
python scripts/load_risk_layer.py

# 4. Sanity check row count
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM risk_points;"
# → 144401

# 5. Run the app locally against Neon
cd app
echo "DATABASE_URL=$DATABASE_URL" > .env.local
npm run dev
# Then run the /api/risk curl commands above.
```
