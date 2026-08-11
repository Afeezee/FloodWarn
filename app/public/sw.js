/**
 * FloodWarn service worker.
 *
 * Design intent:
 *   - Precache the *static* app assets (manifest, icons, risk overlay)
 *     so a return visit works instantly and the last-checked area works
 *     offline. Do NOT cache-first the HTML routes — HTML embeds
 *     hashed JS-chunk references, so a cached HTML pinned to an old
 *     bundle strands users on a broken deploy. HTML uses
 *     stale-while-revalidate instead.
 *   - Cache /api/risk responses per-URL: the last-checked area works
 *     offline. Network-first with cache fallback.
 *   - Never cache /api/geocode error responses; cache successes with
 *     stale-while-revalidate.
 *
 * Bump CACHE_VERSION on any strategy change so old SW installs
 * invalidate their caches on the next activate.
 */

const CACHE_VERSION = "v2";
const SHELL_CACHE = `floodwarn-shell-${CACHE_VERSION}`;
const RUNTIME_CACHE = `floodwarn-runtime-${CACHE_VERSION}`;

// Precache only true static assets, NOT HTML routes.
const SHELL_ASSETS = [
  "/manifest.webmanifest",
  "/icon-192.svg",
  "/icon-512.svg",
  "/icon-maskable.svg",
  "/risk_layer_min.geojson.gz",
];

// HTML routes — cached but always revalidated in the background on
// visit so a new deploy propagates in one page-view.
const HTML_ROUTES = new Set(["/", "/how-it-works", "/map"]);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS).catch(() => {
        /* one asset failing shouldn't wedge the whole install */
      }))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Risk lookup — network-first, fallback to cache, cache successes.
  if (url.pathname === "/api/risk") {
    event.respondWith(networkFirst(req, RUNTIME_CACHE, 8));
    return;
  }
  // Geocode — stale-while-revalidate.
  if (url.pathname === "/api/geocode") {
    event.respondWith(staleWhileRevalidate(req, RUNTIME_CACHE));
    return;
  }
  // HTML routes — stale-while-revalidate so a new deploy shows up on
  // the next visit rather than being pinned by a cached HTML that
  // references old JS chunks.
  if (HTML_ROUTES.has(url.pathname)) {
    event.respondWith(staleWhileRevalidate(req, RUNTIME_CACHE));
    return;
  }
  // Precached static shell assets — cache-first.
  if (SHELL_ASSETS.some((a) => url.pathname === a)) {
    event.respondWith(cacheFirst(req, SHELL_CACHE));
    return;
  }
  // Everything else (Next hashed chunks, images, CSS) — SWR.
  event.respondWith(staleWhileRevalidate(req, RUNTIME_CACHE));
});

async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) cache.put(req, res.clone());
  return res;
}

async function networkFirst(req, cacheName, timeoutSec) {
  const cache = await caches.open(cacheName);
  try {
    const res = await Promise.race([
      fetch(req),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), timeoutSec * 1000)),
    ]);
    if (res && res.ok) {
      cache.put(req, res.clone());
      return res;
    }
    // fall through
  } catch {
    /* fall through to cache */
  }
  const hit = await cache.match(req);
  if (hit) return hit;
  return new Response(
    JSON.stringify({
      offline: true,
      error: "You're offline and this location isn't in your cached history.",
    }),
    { status: 503, headers: { "Content-Type": "application/json" } },
  );
}

async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  const refresh = fetch(req)
    .then((res) => {
      if (res.ok) cache.put(req, res.clone());
      return res;
    })
    .catch(() => hit);
  return hit || refresh;
}
