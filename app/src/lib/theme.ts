/**
 * Design tokens exported to TypeScript so the map (which reads paint
 * values as literals) and the illustration components stay in sync
 * with globals.css. If you edit a colour, edit both.
 */

export const RISK_COLORS = [
  "#F0E1BF",  // No_Flood
  "#E4BC85",  // Low
  "#D48A50",  // Moderate
  "#B15D34",  // High
  "#7A3820",  // Very_High
] as const;

export const RISK_TEXT_ON = [
  "#2C1E12",  // No_Flood
  "#2C1E12",  // Low
  "#FFFCF3",  // Moderate
  "#FFFCF3",  // High
  "#FFFCF3",  // Very_High
] as const;

export const RISK_LABEL = [
  "No flood risk",
  "Low",
  "Moderate",
  "High",
  "Very high",
] as const;

export const RISK_ADVICE = [
  "This area shows no significant flood susceptibility in the model.",
  "Low susceptibility. Awareness during heavy-rain days is a sensible precaution.",
  "Moderate susceptibility. Consider elevating valuables in the wet season and keep drainage around the property clear.",
  "High susceptibility. Have an evacuation plan for peak rainfall periods. Keep sandbags or barriers accessible if the property is at ground level.",
  "Very high susceptibility. Take active precautions during the rainy season: raised storage, clear drainage, and a planned route if evacuation becomes necessary.",
] as const;

export const CANVAS       = "#FBF6EC";
export const CANVAS_ELEV  = "#FFFFFF";
export const INK          = "#2C1E12";
export const INK_SOFT     = "#6B5442";
export const INK_MUTE     = "#A28A72";
export const HAIRLINE     = "#E4D6BE";
export const ACCENT       = "#385A54";
export const ACCENT_SOFT  = "#A6BDB6";
