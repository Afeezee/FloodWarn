import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { lookupRisk } from "@/lib/risk-lookup";

// This handler reads query parameters and executes a DB query per
// request; there is no meaningful build-time output to prerender.
export const dynamic = "force-dynamic";

// Require both parameters as non-empty strings first — Zod's
// `coerce.number()` happily turns `null` into 0, which would silently
// be a valid (but wrong) lat/lng. Once we have a real string, parse
// with Number.parseFloat and range-check.
const coord = (min: number, max: number) =>
  z
    .string()
    .min(1)
    .transform((s) => Number.parseFloat(s))
    .refine((n) => Number.isFinite(n) && n >= min && n <= max, {
      message: `Must be a number in [${min}, ${max}]`,
    });

const Query = z.object({
  lat: coord(-90, 90),
  lng: coord(-180, 180),
});

export async function GET(req: NextRequest) {
  const parsed = Query.safeParse({
    lat: req.nextUrl.searchParams.get("lat") ?? "",
    lng: req.nextUrl.searchParams.get("lng") ?? "",
  });
  if (!parsed.success) {
    return NextResponse.json(
      { error: "lat and lng are required numbers", issues: parsed.error.issues },
      { status: 400 },
    );
  }
  const { lat, lng } = parsed.data;
  try {
    const result = await lookupRisk(lat, lng);
    return NextResponse.json(result, {
      headers: {
        // Same coordinates → same risk. Cache aggressively per-point.
        "Cache-Control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
      },
    });
  } catch (err) {
    console.error("risk lookup failed", err);
    return NextResponse.json(
      { error: "Risk lookup failed. Try again shortly." },
      { status: 500 },
    );
  }
}
