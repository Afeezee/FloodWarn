import type { Metadata, Viewport } from "next";
import { Manrope, Fraunces } from "next/font/google";
import "./globals.css";
import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
  axes: ["opsz", "SOFT"],
});

export const metadata: Metadata = {
  title: "FloodWarn — Ibadan flood risk, explained",
  description:
    "Search or use your location to see the flood susceptibility of any area in Ibadan metropolis, with a short explanation of why.",
  applicationName: "FloodWarn",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "FloodWarn",
    statusBarStyle: "default",
  },
  openGraph: {
    title: "FloodWarn — Ibadan flood risk, explained",
    description:
      "A calm, straightforward flood-risk lookup for the five LGAs of Ibadan.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#FBF6EC",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${manrope.variable} ${fraunces.variable}`}>
      <body className="min-h-dvh antialiased">
        {children}
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
