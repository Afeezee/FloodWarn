/**
 * FloodWarn service worker.
 *
 * Design intent:
 *   - Precache the app shell so a return visit works instantly (and
 *     offline for the shell + gazetteer).
 *   - Cache /api/risk responses per-URL. The last-checked area works
 *     offline because its /api/risk?lat=&lng= response is in the cache.
 *   - The risk overlay (risk_layer_min.geojson.gz) is aggressively
 *     cached because it changes only when the model is retrained.
 *   - Never cache /api/geocode error responses; DO cache successful
 *     ones for a while.
 *
 * Cache-first for static, network-first with cache fallback for the
 * risk API.
 */

const CACHE_VERSION = "v1";
const SHELL_CACHE = `floodwarn-shell-${CACHE_VERSION}`;
const RUNTIME_CACHE = `floodwarn-runtime-${CACHE_VERSION}`;

const SHELL_ASSETS = [
  "/",
  "/how-it-works",
  "/map",
  "/manifest.webmanifest",
  "/icon-192.svg",
  "/icon-512.svg",
  "/icon-maskable.svg",
  "/risk_layer_min.geojson.gz",
];

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
  // Shell assets — cache-first.
  if (SHELL_ASSETS.some((a) => url.pathname === a)) {
    event.respondWith(cacheFirst(req, SHELL_CACHE));
    return;
  }
  // Everything else (Next chunk assets etc.) — cache on success.
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
