import gazetteer from "@/data/gazetteer.json";

type Entry = {
  name: string;
  aliases?: string[];
  lat: number;
  lng: number;
  category: string;
  lga?: string;
};

type Rank = { entry: Entry; score: number };

const ENTRIES: Entry[] = gazetteer.entries as Entry[];

// Very small fuzzy matcher: normalises to lowercase alphanumerics, then
// scores by (a) exact-name match > (b) name starts-with > (c) name/alias
// contains > (d) token-set overlap. Fast enough at ~40 entries that we
// don't need a real index.
function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}

function scoreOne(q: string, entry: Entry): number {
  const nameN = norm(entry.name);
  const aliasesN = (entry.aliases ?? []).map(norm);
  const all = [nameN, ...aliasesN];
  if (all.some((x) => x === q)) return 100;
  if (all.some((x) => x.startsWith(q))) return 80;
  if (all.some((x) => x.includes(q))) return 60;

  // token-set overlap
  const qt = new Set(q.split(" "));
  let best = 0;
  for (const a of all) {
    const at = new Set(a.split(" "));
    const overlap = [...qt].filter((t) => at.has(t)).length;
    best = Math.max(best, overlap * 20);
  }
  return best;
}

export function geocode(query: string, limit = 6): Array<Entry & { score: number }> {
  const q = norm(query);
  if (!q) return [];
  const ranked: Rank[] = ENTRIES
    .map((entry) => ({ entry, score: scoreOne(q, entry) }))
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
  return ranked.map(({ entry, score }) => ({ ...entry, score }));
}

/**
 * Reverse-geocode: find the gazetteer entry nearest to (lat, lng).
 * Great-circle distance via a small-angle approximation — fine at the
 * ~10 km scale of Ibadan metropolis, and much faster than haversine.
 * Returns null if the gazetteer is empty.
 */
export function nearestPlace(
  lat: number,
  lng: number,
): (Entry & { distance_km: number }) | null {
  if (ENTRIES.length === 0) return null;
  const latRad = (lat * Math.PI) / 180;
  const kmPerDegLat = 111.132;
  const kmPerDegLng = 111.32 * Math.cos(latRad);
  let best: Entry | null = null;
  let bestSq = Number.POSITIVE_INFINITY;
  for (const e of ENTRIES) {
    const dy = (e.lat - lat) * kmPerDegLat;
    const dx = (e.lng - lng) * kmPerDegLng;
    const sq = dx * dx + dy * dy;
    if (sq < bestSq) { bestSq = sq; best = e; }
  }
  return best ? { ...best, distance_km: Math.sqrt(bestSq) } : null;
}
