"use client";

import { useMemo, useState, useTransition } from "react";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

function errorMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Unable to start sign-in right now.";
}

type AuthPanelMode = "login" | "signup";

export function SupabaseAuthPanel({
  mode = "login",
  nextPath = "/dashboard",
}: {
  mode?: AuthPanelMode;
  nextPath?: string;
}) {
  const supabase = useMemo(() => createBrowserSupabaseClient(), []);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const redirectTo =
    typeof window === "undefined"
      ? undefined
      : `${window.location.origin}/auth/callback?next=${encodeURIComponent(nextPath)}`;

  function continueWithGoogle() {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      try {
        const { error: authError } = await supabase.auth.signInWithOAuth({
          provider: "google",
          options: redirectTo ? { redirectTo } : undefined,
        });
        if (authError) {
          setError(errorMessage(authError));
        }
      } catch (authError) {
        setError(errorMessage(authError));
      }
    });
  }

  function sendMagicLink() {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      try {
        const { error: authError } = await supabase.auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo: redirectTo,
            shouldCreateUser: mode === "signup",
          },
        });
        if (authError) {
          setError(errorMessage(authError));
          return;
        }

        setNotice(
          mode === "signup"
            ? "Check your email to confirm the account and finish joining the portal."
            : "Check your email for the sign-in link. After the session is created, the backend will resolve your tenant membership and access level.",
        );
      } catch (authError) {
        setError(errorMessage(authError));
      }
    });
  }

  return (
    <div className="space-y-6">
      <button
        type="button"
        className="flex w-full items-center justify-center gap-3 rounded-[8px] border border-line bg-white px-4 py-3 text-sm font-semibold hover:border-ink disabled:cursor-not-allowed disabled:opacity-60"
        onClick={continueWithGoogle}
        disabled={isPending}
      >
        <span className="text-base" aria-hidden="true">
          G
        </span>
        {isPending ? "Opening Google..." : "Continue with Google"}
      </button>

      {error ? (
        <div className="rounded-[8px] border border-rose/30 bg-rose/10 p-4 text-sm leading-6 text-rose">
          {error}
        </div>
      ) : null}

      {notice ? (
        <div className="rounded-[8px] border border-citron/40 bg-citron/20 p-4 text-sm leading-6 text-ink/72">
          {notice}
        </div>
      ) : null}

      <div className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.08em] text-ink/42">
        <span className="h-px flex-1 bg-line" />
        <span>Email link</span>
        <span className="h-px flex-1 bg-line" />
      </div>

      <label className="grid gap-2">
        <span className="text-sm font-semibold">Work email</span>
        <input
          type="email"
          className="h-12 rounded-[8px] border border-line bg-paper px-4 text-sm outline-none focus:border-pine"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
        />
      </label>

      <button
        type="button"
        className="w-full rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine disabled:cursor-not-allowed disabled:opacity-60"
        onClick={sendMagicLink}
        disabled={isPending || !email.trim()}
      >
        {isPending
          ? "Sending..."
          : mode === "signup"
            ? "Email me a sign-up link"
            : "Email me a sign-in link"}
      </button>
    </div>
  );
}
