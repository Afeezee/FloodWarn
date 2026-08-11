import Link from "next/link";
import { RISK_COLORS, RISK_LABEL, RISK_ADVICE } from "@/lib/theme";
import { RiskIllustration, RISK_ORDER } from "@/components/RiskIllustration";

export const metadata = {
  title: "How this works — FloodWarn",
  description:
    "What the FloodWarn model does, what it doesn't, and how to read the risk categories.",
};

export default function HowItWorks() {
  return (
    <main className="min-h-dvh max-w-3xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
        <Link href="/" className="text-sm text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]">
          ← FloodWarn
        </Link>
        <Link href="/map" className="text-sm text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]">
          Map →
        </Link>
      </div>

      <h1 className="font-serif text-4xl sm:text-5xl mb-3">
        How this works
      </h1>
      <p className="text-lg text-[var(--color-ink-soft)] mb-10">
        FloodWarn is a plain-language front end onto a flood <em>susceptibility</em>
        {" "}model for Ibadan metropolis. This page is what we&apos;d want you to know
        before you rely on it.
      </p>

      <section className="space-y-6 text-[var(--color-ink)]">
        <div>
          <h2 className="font-serif text-2xl mb-2">What it is</h2>
          <p className="leading-relaxed text-[var(--color-ink-soft)]">
            A machine-learning model that classifies every ~30 metre patch of
            the five Ibadan LGAs into one of five susceptibility categories,
            using seven physical factors: slope, curvature, aspect,
            topographic wetness (TWI), flow accumulation, drainage density,
            and rainfall. When you search or use your location, we look up the
            nearest classified patch and show you the category plus the
            factors that pushed the model that way.
          </p>
        </div>

        <div>
          <h2 className="font-serif text-2xl mb-2">What it is not</h2>
          <ul className="space-y-3 leading-relaxed text-[var(--color-ink-soft)] list-disc pl-6">
            <li>
              <strong>Not a forecast.</strong> The model does not know
              whether it&apos;s going to rain tomorrow. It reports how vulnerable
              a location is <em>if</em> heavy rain occurs.
            </li>
            <li>
              <strong>Not a warranty.</strong> Real flood risk depends on
              local drainage that our raster inputs can&apos;t see (a blocked
              culvert, new construction, poor site levelling), plus weather
              events we can&apos;t predict.
            </li>
            <li>
              <strong>Not medical/legal/insurance advice.</strong> Use it as
              one signal among several.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="font-serif text-2xl mb-4">The five categories</h2>
          <div className="grid gap-4">
            {RISK_ORDER.map((cls, i) => (
              <div
                key={cls}
                className="rounded-[var(--radius-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas-elev)] p-4 flex gap-4 items-center"
              >
                <div className="w-20 shrink-0">
                  <RiskIllustration risk={cls} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <span
                      className="inline-block w-3 h-3 rounded-full"
                      style={{ background: RISK_COLORS[i] }}
                    />
                    <span className="font-medium">{RISK_LABEL[i]}</span>
                  </div>
                  <p className="mt-1 text-sm text-[var(--color-ink-soft)] leading-relaxed">
                    {RISK_ADVICE[i]}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="font-serif text-2xl mb-2">Why we don&apos;t just use the source label</h2>
          <p className="leading-relaxed text-[var(--color-ink-soft)]">
            The public susceptibility raster we started from turned out to be
            a rule-based binning of one column (drainage density). Building a
            useful predictive model on it would have produced a system that
            looked accurate but ignored the other six factors. So we
            reconstructed the target using a literature-informed weighted
            overlay of all seven factors, retrained the model, and validated
            it under a leave-one-cluster-out protocol so we could report how
            well it transfers to areas it has not seen. The full write-up is
            in the project repository under <code>/reports</code>.
          </p>
        </div>

        <div>
          <h2 className="font-serif text-2xl mb-2">Coverage</h2>
          <p className="leading-relaxed text-[var(--color-ink-soft)]">
            FloodWarn covers the five LGAs of Ibadan metropolis. If you
            search or geolocate somewhere else, we&apos;ll tell you it&apos;s
            outside coverage rather than guess.
          </p>
        </div>
      </section>

      <p className="mt-16 pt-8 border-t border-[var(--color-hairline)] text-sm text-[var(--color-ink-mute)]">
        Built as a thesis project on flood-susceptibility mapping and
        explanation-first delivery for at-risk populations.
      </p>
    </main>
  );
}
