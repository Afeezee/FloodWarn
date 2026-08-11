/**
 * load_neon.mjs — one-shot schema apply + bulk load into Neon over the
 * HTTPS driver.
 *
 * We use @neondatabase/serverless (HTTPS SQL) because the standard
 * PostgreSQL TCP+TLS handshake is intermittently blocked from this
 * network. The driver is fine for both DDL and batched INSERTs; the
 * only trick is that its `sql` tag runs one statement per call, so we
 * split the schema on `;` and batch inserts in chunks.
 *
 * Usage:
 *     cd app
 *     node load_neon.mjs
 */

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { neon } from "@neondatabase/serverless";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SCHEMA_PATH = path.join(ROOT, "db", "schema.sql");
const CSV_PATH = path.join(ROOT, "data", "processed", "risk_layer.csv");

// ---- load env
{
  const envPath = path.resolve(__dirname, ".env.local");
  const raw = fs.readFileSync(envPath, "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|(.*))\s*$/);
    if (m) process.env[m[1]] = m[2] ?? m[3] ?? m[4] ?? "";
  }
}
if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL missing in app/.env.local");
  process.exit(1);
}
const sql = neon(process.env.DATABASE_URL);

// ---- 1. Apply schema
console.log(`[1/3] applying schema from ${SCHEMA_PATH}`);
const rawSchema = fs.readFileSync(SCHEMA_PATH, "utf8");
// Strip line comments FIRST (they may contain ' or "), then split on
// `;` respecting $$-delimited function bodies.
const schema = rawSchema
  .split(/\r?\n/)
  .map((line) => line.replace(/--.*$/, ""))
  .join("\n");
function splitSql(text) {
  const stmts = [];
  let buf = "";
  let inDollar = false;
  let i = 0;
  while (i < text.length) {
    if (text[i] === "$" && text[i + 1] === "$") {
      inDollar = !inDollar;
      buf += "$$";
      i += 2;
      continue;
    }
    if (text[i] === ";" && !inDollar) {
      const s = buf.trim();
      if (s) stmts.push(s);
      buf = "";
      i++;
      continue;
    }
    buf += text[i++];
  }
  const tail = buf.trim();
  if (tail) stmts.push(tail);
  return stmts;
}
for (const stmt of splitSql(schema)) {
  const compact = stmt.trim();
  if (!compact) continue;
  process.stdout.write("  · ");
  console.log(compact.split("\n")[0].slice(0, 70) + "…");
  await sql.query(stmt);
}
console.log("[1/3] schema applied.");

// ---- 2. Bulk-insert risk_points
console.log(`[2/3] streaming ${CSV_PATH}`);

// Count rows for progress
const total = await new Promise((resolve) => {
  let n = -1; // account for header
  const rl = readline.createInterface({
    input: fs.createReadStream(CSV_PATH),
    crlfDelay: Infinity,
  });
  rl.on("line", () => n++);
  rl.on("close", () => resolve(n));
});
console.log(`  ${total.toLocaleString()} rows expected`);

// A CSV parser that respects quoted commas and quoted newlines. Our
// exported file has quoted `explanation` + `top_factors` fields that
// contain commas and — sometimes — newlines. We stream line-by-line
// but treat lines starting inside a quoted field as continuations.
async function* parseCsvRows(filePath) {
  const rl = readline.createInterface({
    input: fs.createReadStream(filePath, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });
  let header = null;
  let carry = "";
  for await (const line of rl) {
    const combined = carry ? carry + "\n" + line : line;
    // Count unescaped quotes: if odd, we're mid-field.
    const quoteCount = (combined.match(/"/g) || []).length;
    if (quoteCount % 2 === 1) {
      carry = combined;
      continue;
    }
    carry = "";
    if (header === null) {
      header = splitCsvLine(combined);
      continue;
    }
    yield Object.fromEntries(
      header.map((h, i) => [h, splitCsvLine(combined)[i]]),
    );
  }
}
function splitCsvLine(line) {
  const cells = [];
  let cur = "";
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQ) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') { inQ = false; }
      else cur += c;
    } else {
      if (c === ",") { cells.push(cur); cur = ""; }
      else if (c === '"') { inQ = true; }
      else cur += c;
    }
  }
  cells.push(cur);
  return cells;
}

// Resume-safe: only TRUNCATE if the table is empty. Otherwise assume
// a prior run got partway and skip already-loaded rows.
const existing = await sql`SELECT COUNT(*)::int AS n FROM risk_points`;
const alreadyLoaded = existing[0].n;
if (alreadyLoaded === 0) {
  console.log("  TRUNCATE risk_points (fresh load)");
  await sql.query("TRUNCATE risk_points RESTART IDENTITY;");
} else {
  console.log(`  resuming — ${alreadyLoaded.toLocaleString()} rows already loaded, skipping ahead`);
}
let toSkip = alreadyLoaded;

const BATCH = 500;
let batch = [];
let done = 0;
const t0 = Date.now();

async function flush() {
  if (batch.length === 0) return;
  const values = batch;
  const params = [
    values.map((r) => Number(r.lon)),
    values.map((r) => Number(r.lat)),
    values.map((r) => r.class),
    values.map((r) => Number(r.class_ord)),
    values.map((r) => Number(r.p_No_Flood)),
    values.map((r) => Number(r.p_Low)),
    values.map((r) => Number(r.p_Moderate)),
    values.map((r) => Number(r.p_High)),
    values.map((r) => Number(r.p_Very_High)),
    values.map((r) => r.explanation),
    // Python's json.dumps emits bare NaN for float NaN — coerce to null.
    values.map((r) => r.top_factors.replace(/\bNaN\b/g, "null")),
  ];
  const stmt = `INSERT INTO risk_points
       (geom, class, class_ord, p_no_flood, p_low, p_moderate,
        p_high, p_very_high, explanation, top_factors)
     SELECT
       ST_SetSRID(ST_MakePoint(u.lon::float8, u.lat::float8), 4326)::geography,
       u.class, u.class_ord::smallint,
       u.p_no_flood::real, u.p_low::real, u.p_moderate::real,
       u.p_high::real, u.p_very_high::real,
       u.explanation, u.top_factors::jsonb
     FROM unnest(
       $1::float8[], $2::float8[], $3::text[], $4::smallint[],
       $5::real[],   $6::real[],   $7::real[], $8::real[],
       $9::real[],   $10::text[],  $11::text[]
     ) AS u(lon, lat, class, class_ord,
            p_no_flood, p_low, p_moderate, p_high, p_very_high,
            explanation, top_factors)`;
  // Retry-on-transient-network — VPNs and Neon HTTPS occasionally reset.
  const maxAttempts = 5;
  for (let attempt = 1; ; attempt++) {
    try {
      await sql.query(stmt, params);
      break;
    } catch (err) {
      const transient =
        (err && err.sourceError && err.sourceError.code === "ECONNRESET") ||
        (err && err.message && /fetch failed|ECONNRESET|ETIMEDOUT|ENETUNREACH/i.test(err.message));
      if (!transient || attempt >= maxAttempts) throw err;
      const backoff = 500 * 2 ** (attempt - 1);
      console.log(`    · transient error (attempt ${attempt}), retrying in ${backoff}ms — ${err.message.split('\n')[0]}`);
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  batch = [];
}

let seen = 0;
for await (const row of parseCsvRows(CSV_PATH)) {
  seen++;
  if (seen <= toSkip) continue;
  batch.push(row);
  if (batch.length >= BATCH) {
    await flush();
    done += BATCH;
    if (done % 10000 === 0 || done === BATCH) {
      const rate = done / ((Date.now() - t0) / 1000);
      const eta = Math.round((total - toSkip - done) / rate);
      console.log(
        `  +${done.toLocaleString()} (total ${(toSkip + done).toLocaleString()}/${total.toLocaleString()})  ` +
          `(${rate.toFixed(0)} rows/s, eta ${eta}s)`,
      );
    }
  }
}
await flush();
done += batch.length;
console.log(`[2/3] loaded ${done.toLocaleString()} rows in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

// ---- 3. Verify
console.log("[3/3] verifying");
const cnt = await sql`SELECT COUNT(*)::int AS n FROM risk_points`;
console.log(`  row count: ${cnt[0].n.toLocaleString()}`);
const dist = await sql`
  SELECT class, COUNT(*)::int AS n
  FROM risk_points GROUP BY class ORDER BY MIN(class_ord)`;
for (const r of dist) console.log(`  ${r.class.padEnd(10)}: ${r.n.toLocaleString()}`);

// A couple of nearest-point queries just to prove the function works
console.log("\n  Nearest-point spot-checks:");
for (const [lat, lng, label] of [
  [7.326389, 3.88, "No_Flood sample"],
  [7.333056, 3.849167, "Very_High sample"],
  [6.5, 3.4, "Lagos (outside)"],
]) {
  const r = await sql.query(
    `SELECT class, distance_m FROM nearest_risk($1, $2)`,
    [lng, lat],
  );
  console.log(
    `    ${label.padEnd(20)} → class=${(r[0]?.class ?? "?").padEnd(10)} ` +
      `dist=${(r[0]?.distance_m ?? -1).toFixed(0)}m`,
  );
}
