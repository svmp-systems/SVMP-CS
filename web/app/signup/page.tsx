import { SupabaseAuthPanel } from "@/components/auth/supabase-auth-panel";
import { isSupabaseConfigured } from "@/lib/portal-auth-env";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export default async function SignUpPage() {
  const supabaseConfigured = isSupabaseConfigured();

  if (supabaseConfigured) {
    const supabase = await createServerSupabaseClient();
    const { data } = await supabase.auth.getClaims();
    if (data?.claims?.sub) {
      redirect("/dashboard");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper p-6 text-ink md:p-10">
      <div className="w-full max-w-md rounded-[8px] border border-line bg-white p-6">
        <p className="text-sm font-semibold text-pine">Invitation access</p>
        <h1 className="mt-3 text-2xl font-semibold">Join your SVMP CS workspace</h1>
        <p className="mt-3 text-sm leading-6 text-ink/62">
          Finish sign-up with the invited work email. Supabase creates the session, and the backend only grants
          dashboard access if that user has an active tenant membership.
        </p>
        <div className="mt-8">
          {supabaseConfigured ? (
            <SupabaseAuthPanel mode="signup" />
          ) : (
            <div className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
              Invitation sign-up is unavailable until Supabase is configured in the live environment.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
