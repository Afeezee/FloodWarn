"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Map as MapLibreMap,
  NavigationControl,
  GeolocateControl,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { baseMapStyle } from "@/lib/basemap-style";
import { RISK_COLORS, RISK_LABEL } from "@/lib/theme";

const IBADAN_CENTER: [number, number] = [3.895, 7.383];
const IBADAN_BOUNDS: [[number, number], [number, number]] = [
  [3.75, 7.25],
  [4.05, 7.5],
];

export default function MapPage() {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!container.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: container.current,
      style: baseMapStyle(),
      center: IBADAN_CENTER,
      zoom: 12,
      minZoom: 10,
      maxZoom: 17,
      maxBounds: IBADAN_BOUNDS,
      attributionControl: { compact: true },
    });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new GeolocateControl({}), "top-right");

    async function loadOverlay() {
      // Overlay is gzipped GeoJSON. Prod path (Vercel + our vercel.json):
      // server sets Content-Encoding: gzip and the fetch stack decodes
      // transparently. Dev path (`next dev`): no such header, so we
      // decode with DecompressionStream client-side.
      const resp = await fetch("/risk_layer_min.geojson.gz");
      const contentEncoding = resp.headers.get("content-encoding");
      if (contentEncoding === "gzip" || contentEncoding === "br") {
        return await resp.json();
      }
      if (!("DecompressionStream" in window) || !resp.body) {
        throw new Error("Browser too old to decompress the map overlay.");
      }
      const ds = new DecompressionStream("gzip");
      const stream = resp.body.pipeThrough(ds);
      const buf = await new Response(stream).arrayBuffer();
      return JSON.parse(new TextDecoder().decode(buf));
    }

    async function attachOverlay() {
      try {
        const data = await loadOverlay();
        // Guard against effect-cleanup races: map may have been removed.
        if (!mapRef.current) return;
        map.addSource("risk", { type: "geojson", data });
        map.addLayer({
          id: "risk-points",
          type: "circle",
          source: "risk",
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              10, 1.2,
              14, 3.2,
              17, 8,
            ],
            "circle-color": [
              "match", ["get", "c"],
              0, RISK_COLORS[0],
              1, RISK_COLORS[1],
              2, RISK_COLORS[2],
              3, RISK_COLORS[3],
              4, RISK_COLORS[4],
              "#999",
            ],
            "circle-opacity": 0.75,
            "circle-stroke-width": 0,
          },
        });
      } catch (err) {
        console.error("[map] risk overlay load failed:", err);
      } finally {
        // Hide the "Loading map…" overlay even if the risk layer failed —
        // basemap is still usable.
        setReady(true);
      }
    }

    if (map.isStyleLoaded()) {
      attachOverlay();
    } else {
      map.on("load", attachOverlay);
    }

    map.on("click", (e: MapMouseEvent) => {
      const { lng, lat } = e.lngLat;
      // Navigate back to homepage carrying lat/lng — homepage lookup path.
      window.location.href = `/?lat=${lat.toFixed(6)}&lng=${lng.toFixed(6)}`;
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <main className="min-h-dvh relative">
      <header className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
        <div className="max-w-6xl mx-auto px-4 pt-4 flex items-center justify-between">
          <Link
            href="/"
            className="pointer-events-auto bg-[var(--color-canvas-elev)]/95 backdrop-blur px-4 py-2 rounded-full text-sm border border-[var(--color-hairline)] shadow-[var(--shadow-soft)]"
          >
            ← Home
          </Link>
          <div className="pointer-events-auto bg-[var(--color-canvas-elev)]/95 backdrop-blur px-4 py-2 rounded-full text-sm border border-[var(--color-hairline)] shadow-[var(--shadow-soft)] hidden sm:block">
            Click anywhere to see the risk for that point.
          </div>
        </div>
      </header>

      <div ref={container} className="absolute inset-0" />

      <div className="absolute bottom-4 left-4 right-4 z-10 pointer-events-none">
        <div className="max-w-md mx-auto bg-[var(--color-canvas-elev)]/95 backdrop-blur rounded-[var(--radius-lg)] shadow-[var(--shadow-soft)] border border-[var(--color-hairline)] p-4 pointer-events-auto">
          <p className="text-xs uppercase tracking-widest text-[var(--color-ink-mute)] mb-2">
            Legend
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
        </div>
      </div>

      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-canvas)]/70 backdrop-blur-sm z-20">
          <p className="text-[var(--color-ink-mute)]">Loading map…</p>
        </div>
      )}
    </main>
  );
}
