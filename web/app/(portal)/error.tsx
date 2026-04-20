"use client";

import Link from "next/link";

export default function PortalRouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper p-6 text-ink md:p-10">
      <div className="w-full max-w-xl rounded-[8px] border border-line bg-white p-6">
        <p className="text-sm font-semibold text-pine">Customer portal</p>
        <h1 className="mt-3 text-3xl font-semibold">This page hit a portal error</h1>
        <p className="mt-4 text-sm leading-6 text-ink/64">
          The portal caught the crash instead of dropping the browser into a blank server-error screen. Try again, or go back to login and start a fresh session.
        </p>
        {error.digest ? (
          <p className="mt-4 rounded-[8px] border border-line bg-paper p-3 text-xs text-ink/56">
            Error digest: {error.digest}
          </p>
        ) : null}
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine"
          >
            Try again
          </button>
          <Link
            href="/login"
            className="rounded-[8px] border border-line px-4 py-3 text-sm font-semibold hover:border-ink"
          >
            Back to login
          </Link>
        </div>
      </div>
    </main>
  );
}
