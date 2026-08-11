import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { geocode } from "@/lib/gazetteer";

const Query = z.object({
  q: z.string().min(1).max(100),
});

export async function GET(req: NextRequest) {
  const parsed = Query.safeParse({
    q: req.nextUrl.searchParams.get("q") ?? "",
  });
  if (!parsed.success) {
    return NextResponse.json(
      { error: "q is required (1-100 chars)", issues: parsed.error.issues },
      { status: 400 },
    );
  }
  const results = geocode(parsed.data.q);
  return NextResponse.json(
    { query: parsed.data.q, results },
    {
      headers: {
        // Gazetteer is static → cache hard.
        "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800",
      },
    },
  );
}
