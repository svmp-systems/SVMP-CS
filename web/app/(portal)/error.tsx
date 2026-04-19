"use client";

export default function PortalError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="rounded-[8px] border border-berry/20 bg-white p-6">
      <p className="text-sm font-semibold text-berry">Portal error</p>
      <h1 className="mt-3 text-2xl font-semibold">The dashboard could not load.</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-ink/64">
        {error.message || "Check Clerk, API URL, CORS, and backend environment variables."}
      </p>
      <button
        onClick={reset}
        className="mt-5 rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine"
      >
        Try again
      </button>
    </div>
  );
}
