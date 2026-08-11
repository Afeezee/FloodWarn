"""
load_risk_layer.py — Bulk-load risk_layer.csv into a Neon PostGIS
database.

Assumes db/schema.sql has already been applied (see its header
comment). Reads DATABASE_URL from the environment.

Design choices:
  - Uses psycopg's COPY protocol via execute_batch for portability; a
    proper COPY FROM stdin would be faster but requires the geography
    column to be pre-computed as WKB and Neon works fine at this size
    (~144k rows) with batched inserts.
  - Batch size 5000 rows.
  - Idempotent: TRUNCATE before insert so re-running gives a clean load.

Usage:
    export DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"
    python scripts/load_risk_layer.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

from _env import load as _load_env, neon_connect_kwargs


ROOT = Path(__file__).resolve().parent.parent
RISK_CSV = ROOT / "data" / "processed" / "risk_layer.csv"


def main() -> None:
    _load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set. Provision a Neon DB and export the "
                 "connection string (with sslmode=require).")
    try:
        import psycopg
        from psycopg.rows import tuple_row
    except ImportError:
        sys.exit("Install psycopg first:  pip install 'psycopg[binary]'")

    print(f"[load] reading {RISK_CSV}")
    df = pd.read_csv(RISK_CSV)
    print(f"[load] rows: {len(df):,}")

    with psycopg.connect(url, row_factory=tuple_row, **neon_connect_kwargs(url)) as conn:
        with conn.cursor() as cur:
            print("[load] TRUNCATE risk_points")
            cur.execute("TRUNCATE risk_points RESTART IDENTITY;")

            print("[load] batch insert")
            t0 = time.time()
            batch_size = 5000
            insert = (
                "INSERT INTO risk_points "
                "(geom, class, class_ord, p_no_flood, p_low, p_moderate, "
                " p_high, p_very_high, explanation, top_factors) "
                "VALUES (ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)"
            )
            for start in range(0, len(df), batch_size):
                chunk = df.iloc[start:start + batch_size]
                rows = [
                    (float(r.lon), float(r.lat),
                     r["class"], int(r.class_ord),
                     float(r.p_No_Flood), float(r.p_Low), float(r.p_Moderate),
                     float(r.p_High), float(r.p_Very_High),
                     r.explanation, r.top_factors)
                    for _, r in chunk.iterrows()
                ]
                cur.executemany(insert, rows)
                if start % 25000 == 0:
                    print(f"  {start + len(chunk):>7,}/{len(df):,}  "
                          f"({time.time()-t0:.1f}s)")

        conn.commit()

    print(f"[load] done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
