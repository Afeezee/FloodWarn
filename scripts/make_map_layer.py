"""
make_map_layer.py — Produce the lightweight map-overlay artefact served
by the Next.js app.

Reads the full risk_layer.geojson (~200 MB, with explanations) and writes:
  app/public/risk_layer_min.geojson.gz   ~1-2 MB — just {lon, lat, class_ord}

The full explanations live only in PostGIS and are fetched per-point by
/api/risk. The map overlay only needs the class colour + point geometry.

Future upgrade path: replace this script with a tippecanoe -> PMTiles
pipeline once tippecanoe is installable (Docker or self-built). The
current MapLibre code will not need to change — swap the URL from
`/risk_layer_min.geojson.gz` to `pmtiles://…risk.pmtiles` and add the
pmtiles protocol register call.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RISK_CSV = ROOT / "data" / "processed" / "risk_layer.csv"
OUT = ROOT / "app" / "public" / "risk_layer_min.geojson.gz"


def main() -> None:
    df = pd.read_csv(RISK_CSV, usecols=["lon", "lat", "class_ord"])
    features = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [round(r.lon, 6), round(r.lat, 6)]},
         "properties": {"c": int(r.class_ord)}}
        for r in df.itertuples(index=False)
    ]
    fc = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(fc, separators=(",", ":")).encode("utf-8")
    with gzip.open(OUT, "wb", compresslevel=9) as f:
        f.write(payload)
    print(f"wrote {OUT}  raw={len(payload):,} bytes  "
          f"gzipped={OUT.stat().st_size:,} bytes  ({len(features):,} points)")


if __name__ == "__main__":
    main()
