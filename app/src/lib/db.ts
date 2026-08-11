import { neon, type NeonQueryFunction } from "@neondatabase/serverless";

/**
 * Neon HTTPS driver — one HTTP round-trip per query, no connection
 * pooling to manage. Works from:
 *   - Vercel serverless / edge (recommended pattern for Neon on Vercel)
 *   - Local dev, including behind restrictive networks where port 5432
 *     is blocked (VPNs, hotel Wi-Fi) because it uses HTTPS 443.
 *
 * Lazy: we do the DATABASE_URL check on first use so Next.js's
 * build-time route metadata pass doesn't crash for developers who
 * haven't wired up the DB yet.
 */

type Sql = NeonQueryFunction<false, false>;

declare global {
  // eslint-disable-next-line no-var
  var _neonSql: Sql | undefined;
}

function makeClient(): Sql {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Provision a Neon database, apply " +
        "db/schema.sql, load with `node app/load_neon.mjs`, then set " +
        "DATABASE_URL in the runtime environment.",
    );
  }
  return neon(url);
}

export function getSql(): Sql {
  if (!globalThis._neonSql) {
    globalThis._neonSql = makeClient();
  }
  return globalThis._neonSql;
}
