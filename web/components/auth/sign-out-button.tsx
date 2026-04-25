"use client";

import { useMemo, useState, useTransition } from "react";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

export function SignOutButton({
  label = "Sign out",
  className,
}: {
  label?: string;
  className?: string;
}) {
  const supabase = useMemo(() => createBrowserSupabaseClient(), []);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function signOut() {
    setError(null);
    startTransition(async () => {
      const { error: authError } = await supabase.auth.signOut();
      if (authError) {
        setError(authError.message);
        return;
      }

      window.location.assign("/login");
    });
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        className={className}
        onClick={signOut}
        disabled={isPending}
      >
        {isPending ? "Signing out..." : label}
      </button>
      {error ? <p className="text-xs text-rose">{error}</p> : null}
    </div>
  );
}
