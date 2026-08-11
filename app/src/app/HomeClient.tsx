"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SearchBar } from "@/components/SearchBar";
import { RiskResult } from "@/components/RiskResult";
import { RISK_COLORS, RISK_LABEL } from "@/lib/theme";
import { nearestPlace } from "@/lib/gazetteer";
import type { RiskLookupResult } from "@/lib/risk-lookup";

type Selected =
  | { kind: "place"; name: string; lat: number; lng: number }
  | null;

export default function HomeClient() {
  const [selected, setSelected] = useState<Selected>(null);
  const [result, setResult] = useState<RiskLookupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runLookup = useCallback(async (place: {
    name: string; lat: number; lng: number;
  }) => {
    setSelected({ kind: "place", ...place });
    setResult(null);
    setError(null);
    setLoading(true);
    try {
      const r = await fetch(`/api/risk?lat=${place.lat}&lng=${place.lng}`);
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as RiskLookupResult;
      setResult(data);
    } catch (err) {
      setError(
        "Couldn't load flood-risk data. Check your connection and try again."
      );
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setSelected(null);
    setResult(null);
    setError(null);
  }, []);

  const search = useSearchParams();
  useEffect(() => {
    const lat = search.get("lat");
    const lng = search.get("lng");
    if (lat && lng && !selected) {
      const la = Number(lat);
      const lo = Number(lng);
      if (Number.isFinite(la) && Number.isFinite(lo)) {
        // Reverse-geocode: always attach the nearest known place so
        // the results page tells the user WHERE they clicked in
        // human-readable terms. Ibadan metropolis is ~12 km across —
        // any click within the coverage area is by definition close
        // to at least one of the ~40 gazetteer entries. Only fall
        // back to "Selected point" if the coord is far from all
        // known places (i.e. probably outside coverage).
        const near = nearestPlace(la, lo);
        const name =
          near && near.distance_km < 8
            ? `Near ${near.name}`
            : "Selected point";
        runLookup({ name, lat: la, lng: lo });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-dvh flex flex-col">
      <header className="px-6 pt-8 pb-4 flex items-center justify-between max-w-6xl mx-auto w-full">
        <Link href="/" className="flex items-center gap-2 group" onClick={reset}>
          <span className="text-xl font-serif tracking-tight">FloodWarn</span>
          <span className="text-[11px] uppercase tracking-widest text-[var(--color-ink-mute)] mt-1">
            Ibadan
          </span>
        </Link>
        <nav className="flex items-center gap-5 text-sm text-[var(--color-ink-soft)]">
          <Link href="/map" className="hover:text-[var(--color-ink)]">
            Map
          </Link>
          <Link href="/how-it-works" className="hover:text-[var(--color-ink)]">
            How it works
          </Link>
        </nav>
      </header>

      <section className="flex-1 flex flex-col items-center justify-center px-6 pb-16">
        {!selected && (
          <div className="w-full">
            <div className="text-center mb-10">
              <h1 className="font-serif text-5xl sm:text-6xl leading-tight max-w-3xl mx-auto">
                Flood risk for your neighbourhood, in one look.
              </h1>
              <p className="mt-5 text-lg text-[var(--color-ink-soft)] max-w-xl mx-auto">
                Search an area in Ibadan metropolis, or use your location. We&apos;ll
                show the susceptibility rating and the factors that drive it.
              </p>
            </div>
            <SearchBar onPick={runLookup} disabled={loading} />
            <Legend />
          </div>
        )}

        {selected && (
          <div className="w-full">
            <RiskResult
              place={selected.name}
              coords={{ lat: selected.lat, lng: selected.lng }}
              result={result}
              onReset={reset}
            />
            {error && (
              <p className="mt-8 text-center text-[var(--color-risk-3)]">
                {error}{" "}
                <button
                  onClick={() => runLookup(selected)}
                  className="underline"
                >
                  Retry
                </button>
              </p>
            )}
          </div>
        )}
      </section>

      <footer className="text-center text-xs text-[var(--color-ink-mute)] pb-8">
        Susceptibility model, not a real-time forecast. See{" "}
        <Link href="/how-it-works" className="underline">
          how this works
        </Link>
        .
      </footer>
    </main>
  );
}

function Legend() {
  return (
    <div className="mt-14 max-w-xl mx-auto">
      <p className="text-xs uppercase tracking-widest text-[var(--color-ink-mute)] text-center mb-3">
        Risk scale
      </p>
      <div className="rounded-full overflow-hidden flex h-3">
        {RISK_COLORS.map((c, i) => (
          <div key={i} style={{ background: c }} className="flex-1" />
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-[var(--color-ink-mute)]">
        {RISK_LABEL.map((l) => (
          <span key={l}>{l}</span>
        ))}
      </div>
    </div>
  );
}
