import { Suspense } from "react";
import HomeClient from "./HomeClient";

// The client component uses useSearchParams(), which requires a
// Suspense boundary so Next can bail out of static prerender only for
// the searchparams-sensitive subtree. The shell around it can still be
// server-rendered instantly.
export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-dvh" />}>
      <HomeClient />
    </Suspense>
  );
}
