"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import L, { Map as LeafletMap, LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";

import { RISK_COLORS, RISK_LABEL } from "@/lib/theme";

// Actual grid coverage bounds (from data/processed/profile.json — the
// true extent of the 144,401 precomputed points). The map viewport is
// wider so the boundary reads clearly, but /api/risk will only return
// a real class for clicks INSIDE this polygon.
const COVERAGE_BOUNDS: L.LatLngTuple[] = [
  [7.311, 3.831], // SW
  [7.311, 3.955], // SE
  [7.443, 3.955], // NE
  [7.443, 3.831], // NW
  [7.311, 3.831], // close ring
];

const IBADAN_CENTER: [number, number] = [7.378, 3.893];
const IBADAN_VIEW_BOUNDS: LatLngBoundsExpression = [
  [7.25, 3.75],
  [7.5, 4.05],
];

export default function MapPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: IBADAN_CENTER,
      zoom: 12,
      minZoom: 10,
      maxZoom: 17,
      maxBounds: IBADAN_VIEW_BOUNDS,
      zoomControl: true,
      attributionControl: true,
    });
    mapRef.current = map;

    // Basemap: Carto Voyager (with labels) — muted, warm palette.
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
      {
        subdomains: ["a", "b", "c", "d"],
        maxZoom: 19,
        attribution:
          '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>',
      },
    ).addTo(map);

    // Dashed red boundary marking the FloodWarn coverage area, plus a
    // very faint tinted fill so users immediately see what's inside vs
    // outside coverage.
    L.polygon(COVERAGE_BOUNDS, {
      color: "#B15D34",      // terracotta from our palette
      weight: 2,
      dashArray: "6 6",
      fill: true,
      fillColor: "#B15D34",
      fillOpacity: 0.05,
      interactive: false,     // don't intercept clicks — let the map handler run
    }).addTo(map);

    // Small "Coverage area" label anchored inside the polygon so
    // users understand what the dashed box means.
    L.marker([7.437, 3.836], {
      icon: L.divIcon({
        className: "coverage-label",
        html: '<span style="background:rgba(251,246,236,0.95);border:1px solid #E4D6BE;color:#7A3820;font-size:10px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;padding:2px 8px;border-radius:999px;white-space:nowrap;box-shadow:0 4px 10px -6px rgba(44,30,18,0.25)">Coverage area</span>',
        iconSize: [110, 20],
        iconAnchor: [0, 0],
      }),
      interactive: false,
      keyboard: false,
    }).addTo(map);

    // Click → home page with lat/lng in URL so the same result-reveal
    // flow runs. /api/risk will report coverage_ok=false for points
    // outside the coverage polygon (>200m from any grid cell).
    map.on("click", (e) => {
      const { lat, lng } = e.latlng;
      window.location.href = `/?lat=${lat.toFixed(6)}&lng=${lng.toFixed(6)}`;
    });

    setReady(true);

    return () => {
      map.remove();
      if (mapRef.current === map) mapRef.current = null;
    };
  }, []);

  return (
    <main className="h-dvh w-screen relative overflow-hidden">
      <header className="absolute top-0 left-0 right-0 z-[1000] pointer-events-none">
        <div className="max-w-6xl mx-auto px-4 pt-4 flex items-center justify-between">
          <Link
            href="/"
            className="pointer-events-auto bg-[var(--color-canvas-elev)]/95 backdrop-blur px-4 py-2 rounded-full text-sm border border-[var(--color-hairline)] shadow-[var(--shadow-soft)]"
          >
            ← Home
          </Link>
          <div className="pointer-events-auto bg-[var(--color-canvas-elev)]/95 backdrop-blur px-4 py-2 rounded-full text-sm border border-[var(--color-hairline)] shadow-[var(--shadow-soft)] hidden sm:block">
            Click inside the outlined area to see the risk for that point.
          </div>
        </div>
      </header>

      <div ref={containerRef} className="h-dvh w-full z-0" />

      <div className="absolute bottom-4 left-4 right-4 z-[1000] pointer-events-none">
        <div className="max-w-md mx-auto bg-[var(--color-canvas-elev)]/95 backdrop-blur rounded-[var(--radius-lg)] shadow-[var(--shadow-soft)] border border-[var(--color-hairline)] p-4 pointer-events-auto">
          <p className="text-xs uppercase tracking-widest text-[var(--color-ink-mute)] mb-2">
            Risk scale
          </p>
          <div className="rounded-full overflow-hidden flex h-3">
            {RISK_COLORS.map((c, i) => (
              <div key={i} style={{ background: c }} className="flex-1" />
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-[var(--color-ink-mute)]">
            {RISK_LABEL.map((l) => (
              <span key={l}>{l}</span>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-[var(--color-ink-mute)] leading-snug">
            The dashed area is the FloodWarn coverage grid. Click any
            point inside to see its rating and the factors behind it.
          </p>
        </div>
      </div>

      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-canvas)]/70 backdrop-blur-sm z-[500]">
          <p className="text-[var(--color-ink-mute)]">Loading map…</p>
        </div>
      )}
    </main>
  );
}
