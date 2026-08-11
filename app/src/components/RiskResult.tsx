"use client";

import { motion, AnimatePresence } from "framer-motion";
import { RISK_LABEL, RISK_ADVICE, RISK_COLORS, RISK_TEXT_ON } from "@/lib/theme";
import { RiskIllustration } from "./RiskIllustration";
import type { RiskLookupResult } from "@/lib/risk-lookup";

type Class = "No_Flood" | "Low" | "Moderate" | "High" | "Very_High";

export function RiskResult({
  place,
  result,
  onReset,
}: {
  place: string;
  result: RiskLookupResult | null;
  onReset: () => void;
}) {
  if (result === null) {
    return (
      <div className="text-center py-16 text-[var(--color-ink-mute)]">
        Looking up…
      </div>
    );
  }

  if (!result.coverage_ok) {
    return (
      <div className="max-w-xl mx-auto text-center py-12 px-6">
        <p className="font-serif text-2xl mb-3">
          Outside coverage
        </p>
        <p className="text-[var(--color-ink-soft)] mb-6">
          {result.message}
        </p>
        <button
          onClick={onReset}
          className="text-[var(--color-accent)] underline underline-offset-4"
        >
          Try another area
        </button>
      </div>
    );
  }

  const cls = result.class as Class;
  const idx = result.class_ord;
  const surface = RISK_COLORS[idx];
  const textColor = RISK_TEXT_ON[idx];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={`${place}-${cls}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-3xl mx-auto"
      >
        <motion.header
          initial={{ y: 12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.05, duration: 0.4 }}
          className="text-center mb-6"
        >
          <p className="text-[var(--color-ink-mute)] text-sm tracking-wider uppercase">
            {place}
          </p>
          <h1 className="font-serif text-4xl sm:text-5xl mt-2">
            {RISK_LABEL[idx]}
          </h1>
        </motion.header>

        <motion.div
          initial={{ scale: 0.98, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          transition={{ delay: 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="rounded-[var(--radius-xl)] p-8 sm:p-10 shadow-[var(--shadow-lift)]"
          style={{ background: surface, color: textColor }}
        >
          <div className="grid sm:grid-cols-[220px_1fr] gap-8 items-center">
            <div className="w-40 sm:w-full mx-auto">
              <RiskIllustration risk={cls} />
            </div>
            <div>
              <p className="text-lg leading-relaxed opacity-95">
                {RISK_ADVICE[idx]}
              </p>
              <div className="mt-6 pt-6 border-t border-current/20 space-y-2 text-sm opacity-90">
                <p className="uppercase tracking-wider text-xs opacity-70">
                  Main contributing factors
                </p>
                <ul className="space-y-1">
                  {result.top_factors.map((f) => (
                    <li key={f.feature}>
                      <span className="font-medium">{f.human_name}</span>
                      {" — "}
                      <span className="opacity-80">{f.phrase}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.4 }}
          className="mt-6 flex flex-wrap gap-3 items-center justify-center text-sm"
        >
          <span className="text-[var(--color-ink-mute)]">
            Model confidence{" "}
            <span className="font-medium text-[var(--color-ink)]">
              {Math.round(result.probabilities[cls] * 100)}%
            </span>
          </span>
          <span className="text-[var(--color-hairline)]">·</span>
          <a
            href={`/map?lat=${result.distance_m > 0 ? "" : ""}`}
            className="text-[var(--color-accent)] underline underline-offset-4"
          >
            See on the map
          </a>
          <span className="text-[var(--color-hairline)]">·</span>
          <button
            onClick={onReset}
            className="text-[var(--color-accent)] underline underline-offset-4"
          >
            Check another area
          </button>
        </motion.div>

        <motion.details
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.4 }}
          className="mt-8 max-w-xl mx-auto text-sm text-[var(--color-ink-soft)]"
        >
          <summary className="cursor-pointer text-[var(--color-accent)]">
            Full explanation
          </summary>
          <p className="mt-2 leading-relaxed">{result.explanation}</p>
        </motion.details>
      </motion.div>
    </AnimatePresence>
  );
}
