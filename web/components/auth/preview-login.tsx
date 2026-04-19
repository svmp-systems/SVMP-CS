"use client";

import { useState, useTransition } from "react";

export function PreviewLogin({ nextPath = "/dashboard" }: { nextPath?: string }) {
  const [email, setEmail] = useState("prnvvh@gmail.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function openPortal() {
    setError(null);
    startTransition(async () => {
      const response = await fetch("/api/preview-login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password, next: nextPath }),
      });
      const payload = (await response.json().catch(() => null)) as {
        redirectTo?: string;
        error?: string;
      } | null;

      if (!response.ok) {
        setError(payload?.error ?? "Unable to sign in.");
        return;
      }

      window.location.assign(payload?.redirectTo ?? "/dashboard");
    });
  }

  return (
    <div className="space-y-5">
      <div className="rounded-[8px] border border-citron bg-citron/20 p-4 text-sm leading-6 text-ink/72">
        Built-in login is on. The portal only opens for allowed emails with the shared portal password.
      </div>

      <label className="grid gap-2">
        <span className="text-sm font-semibold">Portal email</span>
        <input
          type="email"
          className="h-12 rounded-[8px] border border-line bg-paper px-4 text-sm outline-none focus:border-pine"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>

      <label className="grid gap-2">
        <span className="text-sm font-semibold">Portal password</span>
        <input
          type="password"
          className="h-12 rounded-[8px] border border-line bg-paper px-4 text-sm outline-none focus:border-pine"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>

      {error ? (
        <div className="rounded-[8px] border border-rose/30 bg-rose/10 p-4 text-sm leading-6 text-rose">
          {error}
        </div>
      ) : null}

      <button
        type="button"
        className="w-full rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine disabled:cursor-not-allowed disabled:opacity-60"
        onClick={openPortal}
        disabled={isPending || !email.trim() || !password}
      >
        {isPending ? "Opening..." : "Open customer portal"}
      </button>

      <div className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
        Clerk is paused for now. When we are ready, setting{" "}
        <span className="font-semibold">NEXT_PUBLIC_PORTAL_AUTH_MODE=clerk</span> turns Clerk back on.
      </div>
    </div>
  );
}
