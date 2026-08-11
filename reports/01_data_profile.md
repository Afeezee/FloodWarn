# 01 — Data profile: Ibadan Metropolis Flood Dataset

- File: `data\raw\Ibadan_Metropolis_Flood_Dataset.csv`
- Rows: **144,401** (expected 144,401, delta +0)
- Columns: **10** (expected 10)
- Schema matches brief: **YES**
- Header normalisation: stripped trailing space on `Curvature`

## SUSCEP target
- Unexpected labels: none

| Class | Count | Share |
|---|---:|---:|
| No_Flood | 16,126 | 11.2% |
| Low | 32,252 | 22.3% |
| Moderate | 38,116 | 26.4% |
| High | 34,451 | 23.9% |
| Very_High | 23,456 | 16.2% |

## Spatial sanity (Ibadan bbox check)
- Longitude in [3.75, 4.1]: **100.0%** of rows
- Latitude in [7.25, 7.55]: **100.0%** of rows
- Actual X (lon) range: [3.8311, 3.9544]
- Actual Y (lat) range: [7.3114, 7.4431]

## Continuous feature statistics
| col | dtype | nulls | min | p01 | median | mean | p99 | max | std |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| X | float64 | 0 (0.0%) | 3.831 | 3.837 | 3.892 | 3.892 | 3.946 | 3.954 | 0.02789 |
| Y | float64 | 0 (0.0%) | 7.311 | 7.315 | 7.374 | 7.375 | 7.437 | 7.443 | 0.03246 |
| Slope | float64 | 282 (0.1953%) | -3.403e+38 | 10.02 | 61.98 | -2.503e+35 | 80.39 | 86.58 | 9.225e+36 |
| Curvature | float64 | 0 (0.0%) | -3.403e+38 | -1.037e+10 | 0 | -8.342e+35 | 1.037e+10 | 3.888e+10 | 1.683e+37 |
| Aspect | float64 | 0 (0.0%) | -3.403e+38 | 0 | 189.5 | -1.673e+35 | 353.7 | 359.1 | 7.544e+36 |
| TWI | float64 | 0 (0.0%) | -3.403e+38 | -9.723 | -8.007 | -2.121e+34 | 1.058 | 11.68 | 2.686e+36 |
| FA | float64 | 0 (0.0%) | -3.403e+38 | 0 | 1 | -2.121e+35 | 5505 | 4.579e+05 | 8.493e+36 |
| Drainage | float64 | 0 (0.0%) | 203.7 | 203.8 | 220.6 | 219.7 | 234.9 | 235.4 | 7.058 |
| Rainfall | float64 | 0 (0.0%) | 59.54 | 59.54 | 73.87 | 74.79 | 101.5 | 101.5 | 8.892 |

## NoData sentinel audit
- Threshold: any value <= -1e+30 treated as GDAL/ArcGIS NoData (-FLT_MAX).

| column | sentinel rows |
|---|---:|
| Slope | 106 |
| Curvature | 354 |
| Aspect | 71 |
| TWI | 9 |
| FA | 90 |

- **Rows with a sentinel in >=1 of those columns: 368 (0.25%)**
- Curvature |max| after sentinel removal: **3.888e+10** (still scaled ~1e10 vs. textbook ±0.1; see decision 2 below).

## Decisions (agreed with user, 2026-08-10)
1. **Slope explicit nulls (282) + all NoData sentinels above** → median-imputed inside the preprocessing pipeline (Task 3). Keeps all 144,401 grid points for the precomputed risk layer so every resident gets a prediction; imputation limitation documented in the eval report.

2. **Curvature scale (~1e10)** — left as-is. StandardScaler in the preprocessing pipeline neutralises the scale before training; relative structure is preserved. Flagged here for the thesis write-up.

3. **Class balance** — max/min ratio is well under 3x. Class-weighted loss used, no resampling required.