"use client";

import { useEffect, useRef, useState } from "react";

export type GazetteerHit = {
  name: string;
  aliases?: string[];
  lat: number;
  lng: number;
  category: string;
  lga?: string;
  score: number;
};

export function SearchBar({
  onPick,
  disabled,
}: {
  onPick: (hit: GazetteerHit | { lat: number; lng: number; name: string }) => void;
  disabled?: boolean;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<GazetteerHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [geoLoading, setGeoLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await fetch(
          `/api/geocode?q=${encodeURIComponent(q.trim())}`,
          { signal: ctrl.signal },
        );
        if (!r.ok) throw new Error(String(r.status));
        const data = (await r.json()) as { results: GazetteerHit[] };
        setHits(data.results ?? []);
      } catch (err) {
        if ((err as Error).name !== "AbortError") setHits([]);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  function useMyLocation() {
    if (!("geolocation" in navigator)) {
      alert("This browser doesn't support geolocation.");
      return;
    }
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoLoading(false);
        onPick({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          name: "Your location",
        });
      },
      (err) => {
        setGeoLoading(false);
        alert(
          err.code === err.PERMISSION_DENIED
            ? "Location permission denied. You can search for an area name instead."
            : "Couldn't get your location. Try searching instead.",
        );
      },
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="relative">
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search an area — Bodija, Molete, UI, Ring Road…"
          className="w-full h-14 rounded-[var(--radius-lg)] bg-[var(--color-canvas-elev)] border border-[var(--color-hairline)] px-5 pr-14 text-base outline-none focus:border-[var(--color-accent-soft)] focus:ring-2 focus:ring-[var(--color-accent-soft)]/30 transition"
          disabled={disabled}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          onClick={useMyLocation}
          disabled={disabled || geoLoading}
          className="absolute right-2 top-1/2 -translate-y-1/2 h-10 px-3 rounded-full bg-[var(--color-accent)] text-white text-sm font-medium disabled:opacity-60"
          aria-label="Use my location"
          title="Use my location"
        >
          {geoLoading ? "…" : "Use my location"}
        </button>
      </div>

      {(hits.length > 0 || (loading && q.trim().length >= 2)) && (
        <ul className="mt-2 rounded-[var(--radius-lg)] bg-[var(--color-canvas-elev)] border border-[var(--color-hairline)] shadow-[var(--shadow-soft)] overflow-hidden">
          {loading && (
            <li className="px-5 py-3 text-[var(--color-ink-mute)] text-sm">
              searching…
            </li>
          )}
          {!loading &&
            hits.map((h) => (
              <li key={`${h.name}-${h.lat}`}>
                <button
                  onClick={() => onPick(h)}
                  className="w-full text-left px-5 py-3 hover:bg-[var(--color-canvas-dim)] transition flex items-baseline justify-between gap-4"
                >
                  <span className="font-medium">{h.name}</span>
                  <span className="text-xs text-[var(--color-ink-mute)]">
                    {h.lga ?? h.category}
                  </span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
