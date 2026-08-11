/**
 * Five bespoke illustrations, one per SUSCEP class. Cohesive style:
 *   - Same 240×240 viewbox and same visual "eye level" (horizon at y=170)
 *   - Same warm palette drawn from the app's risk tokens
 *   - Same architectural motif (single dwelling on a plot) so the
 *     progression reads as *this house* under different water levels
 *   - Flat, no gradients (except sky), stroke-less shapes
 *
 * Rendered inline so they work under strict CSP, in the results reveal,
 * on the map legend, and on the "how it works" page.
 */

import * as React from "react";

type Class = "No_Flood" | "Low" | "Moderate" | "High" | "Very_High";

const PALETTE = {
  sky_calm:   "#F8ECD2",
  sky_grey:   "#D6C7AE",
  sky_storm:  "#7A6A55",
  ground:     "#C9AF87",
  ground_wet: "#8E7853",
  house:      "#FBF6EC",
  house_dark: "#7A3820",
  roof:       "#B15D34",
  water_calm: "#8CB4A8",
  water_mid:  "#5F8B85",
  water_hi:   "#385A54",
  sun:        "#E4BC85",
  cloud:      "#EAD9BB",
  rain:       "#385A54",
  accent:     "#7A3820",
};

function Base({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 240 240"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      className="block w-full h-auto"
    >
      {children}
    </svg>
  );
}

function House({ waterAtY }: { waterAtY?: number }) {
  // House body: 90×70 rect centered around x=120, resting on y=170.
  // Roof: triangle sitting on the top edge.
  return (
    <g>
      {/* body */}
      <rect x="75" y="100" width="90" height="70" fill={PALETTE.house} />
      {/* roof */}
      <polygon points="65,100 175,100 120,60" fill={PALETTE.roof} />
      {/* chimney */}
      <rect x="145" y="70" width="10" height="18" fill={PALETTE.house_dark} />
      {/* door */}
      <rect x="108" y="135" width="20" height="35" fill={PALETTE.house_dark} />
      {/* window */}
      <rect x="82" y="115" width="18" height="18" fill={PALETTE.house_dark} />
      <rect x="140" y="115" width="18" height="18" fill={PALETTE.house_dark} />
      {/* subtle window frame */}
      <line x1="91" y1="115" x2="91" y2="133" stroke={PALETTE.house} strokeWidth="1.5" />
      <line x1="82" y1="124" x2="100" y2="124" stroke={PALETTE.house} strokeWidth="1.5" />
      <line x1="149" y1="115" x2="149" y2="133" stroke={PALETTE.house} strokeWidth="1.5" />
      <line x1="140" y1="124" x2="158" y2="124" stroke={PALETTE.house} strokeWidth="1.5" />

      {waterAtY !== undefined && (
        <>
          {/* water overlay, clipped to visible area */}
          <rect
            x="0" y={waterAtY} width="240" height={240 - waterAtY}
            fill={
              waterAtY <= 100 ? PALETTE.water_hi :
              waterAtY <= 140 ? PALETTE.water_mid : PALETTE.water_calm
            }
            opacity="0.85"
          />
        </>
      )}
    </g>
  );
}

function Cloud({ x, y, scale = 1, tone = PALETTE.cloud }: {
  x: number; y: number; scale?: number; tone?: string;
}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <ellipse cx="0"  cy="0" rx="18" ry="10" fill={tone} />
      <ellipse cx="14" cy="-4" rx="14" ry="10" fill={tone} />
      <ellipse cx="-12" cy="-2" rx="12" ry="9" fill={tone} />
    </g>
  );
}

function Raindrop({ x, y }: { x: number; y: number }) {
  return (
    <line x1={x} y1={y} x2={x - 2} y2={y + 8}
          stroke={PALETTE.rain} strokeWidth="2" strokeLinecap="round" />
  );
}

/* ---------- Individual illustrations ---------- */

function NoFlood() {
  return (
    <Base>
      <rect width="240" height="240" fill={PALETTE.sky_calm} />
      {/* sun */}
      <circle cx="40" cy="50" r="18" fill={PALETTE.sun} />
      {/* ground */}
      <rect x="0" y="170" width="240" height="70" fill={PALETTE.ground} />
      <House />
      {/* small tree */}
      <rect x="196" y="140" width="4" height="30" fill={PALETTE.house_dark} />
      <circle cx="198" cy="138" r="12" fill={PALETTE.accent} opacity="0.55" />
    </Base>
  );
}

function LowRisk() {
  return (
    <Base>
      <rect width="240" height="240" fill={PALETTE.sky_calm} />
      <Cloud x={60} y={40} scale={1.1} />
      <rect x="0" y="170" width="240" height="70" fill={PALETTE.ground} />
      <House />
      {/* tiny puddle */}
      <ellipse cx="55" cy="200" rx="18" ry="4" fill={PALETTE.water_calm} opacity="0.7" />
    </Base>
  );
}

function ModerateRisk() {
  return (
    <Base>
      <rect width="240" height="240" fill={PALETTE.sky_grey} />
      <Cloud x={70} y={35} scale={1.2} />
      <Cloud x={175} y={50} scale={0.9} />
      <rect x="0" y="170" width="240" height="70" fill={PALETTE.ground_wet} />
      <House waterAtY={195} />
      {/* light rain */}
      {[60, 100, 150, 200].map((x, i) => (
        <Raindrop key={i} x={x} y={80 + (i % 2) * 6} />
      ))}
    </Base>
  );
}

function HighRisk() {
  return (
    <Base>
      <rect width="240" height="240" fill={PALETTE.sky_grey} />
      <Cloud x={55} y={35} scale={1.3} tone={PALETTE.cloud} />
      <Cloud x={170} y={45} scale={1.2} tone={PALETTE.cloud} />
      <rect x="0" y="170" width="240" height="70" fill={PALETTE.ground_wet} />
      <House waterAtY={160} />
      {/* heavy rain */}
      {Array.from({ length: 14 }).map((_, i) => (
        <Raindrop key={i} x={20 + i * 15} y={70 + (i % 3) * 8} />
      ))}
    </Base>
  );
}

function VeryHigh() {
  return (
    <Base>
      <rect width="240" height="240" fill={PALETTE.sky_storm} />
      <Cloud x={60} y={30} scale={1.4} tone="#B5A38A" />
      <Cloud x={180} y={50} scale={1.4} tone="#B5A38A" />
      <rect x="0" y="170" width="240" height="70" fill={PALETTE.ground_wet} />
      <House waterAtY={125} />
      {/* torrential rain */}
      {Array.from({ length: 22 }).map((_, i) => (
        <Raindrop key={i} x={10 + i * 11} y={65 + (i % 4) * 10} />
      ))}
    </Base>
  );
}

/* ---------- Export ---------- */

const REGISTRY: Record<Class, React.FC> = {
  No_Flood: NoFlood,
  Low: LowRisk,
  Moderate: ModerateRisk,
  High: HighRisk,
  Very_High: VeryHigh,
};

export function RiskIllustration({ risk }: { risk: Class }) {
  const Component = REGISTRY[risk];
  return <Component />;
}

export const RISK_ORDER: Class[] = [
  "No_Flood", "Low", "Moderate", "High", "Very_High",
];
