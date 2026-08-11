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
