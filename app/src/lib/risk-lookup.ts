import { getSql } from "./db";

export type RiskClass =
  | "No_Flood" | "Low" | "Moderate" | "High" | "Very_High";

export type TopFactor = {
  feature: string;
  human_name: string;
  value: number | null;
  shap: number;
  z: number | null;
  phrase: string;
};

export type RiskLookupResult =
  | {
      coverage_ok: true;
      class: RiskClass;
      class_ord: number;
      probabilities: Record<RiskClass, number>;
      explanation: string;
      top_factors: TopFactor[];
      distance_m: number;
    }
  | {
      coverage_ok: false;
      distance_m: number;
      message: string;
    };

// A point >200 m from any grid cell is treated as outside our coverage
// area (the study grid is at ~30 m spacing).
export const COVERAGE_RADIUS_M = 200;

type Row = {
  class: RiskClass;
  class_ord: number;
  p_no_flood: number;
  p_low: number;
  p_moderate: number;
  p_high: number;
  p_very_high: number;
  explanation: string;
  top_factors: TopFactor[] | string;
  distance_m: number;
};

export async function lookupRisk(
  lat: number,
  lng: number,
): Promise<RiskLookupResult> {
  const sql = getSql();
  const rows = (await sql`SELECT * FROM nearest_risk(${lng}, ${lat})`) as Row[];

  if (rows.length === 0) {
    return {
      coverage_ok: false,
      distance_m: Infinity,
      message: "No risk data available.",
    };
  }
  const r = rows[0];
  if (r.distance_m > COVERAGE_RADIUS_M) {
    return {
      coverage_ok: false,
      distance_m: r.distance_m,
      message:
        "This location is outside the Ibadan metropolis coverage area. " +
        "FloodWarn covers the five LGAs of Ibadan; other regions are not modelled.",
    };
  }
  // jsonb comes back parsed already, but if the driver returned it as a
  // string for some reason we normalise here.
  const top_factors: TopFactor[] =
    typeof r.top_factors === "string"
      ? (JSON.parse(r.top_factors) as TopFactor[])
      : r.top_factors;

  return {
    coverage_ok: true,
    class: r.class,
    class_ord: r.class_ord,
    probabilities: {
      No_Flood: r.p_no_flood,
      Low: r.p_low,
      Moderate: r.p_moderate,
      High: r.p_high,
      Very_High: r.p_very_high,
    },
    explanation: r.explanation,
    top_factors,
    distance_m: r.distance_m,
  };
}
