"""
apply_schema.py — Applies db/schema.sql to the database in DATABASE_URL.

Reads DATABASE_URL from app/.env.local if not already in the environment.
Uses psycopg (no psql client required).

Usage:
    python scripts/apply_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from _env import load as _load_env, neon_connect_kwargs


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = ROOT / "db" / "schema.sql"


def main() -> None:
    _load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set (looked in env and app/.env.local).")

    try:
        import psycopg
    except ImportError:
        sys.exit("Install psycopg first:  pip install 'psycopg[binary]'")

    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    print(f"[schema] applying {SCHEMA_SQL} to {url.split('@')[-1].split('/')[0]}")
    kwargs = neon_connect_kwargs(url)
    with psycopg.connect(url, autocommit=True, **kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("[schema] done — risk_points table + GiST index + nearest_risk() created.")


if __name__ == "__main__":
    main()
