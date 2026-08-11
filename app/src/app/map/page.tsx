"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window` at module load time — dodge SSR entirely.
const MapClient = dynamic(() => import("./MapClient"), {
  ssr: false,
  loading: () => (
    <div className="min-h-dvh w-full flex items-center justify-center bg-[var(--color-canvas)]">
      <p className="text-[var(--color-ink-mute)]">Loading map…</p>
    </div>
  ),
});

export default function MapPage() {
  return <MapClient />;
}
