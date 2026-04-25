import Link from "next/link";
import { isSupabaseConfigured } from "@/lib/portal-auth-env";

export default function LoginVerifyPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper p-6 text-ink md:p-10">
      <div className="w-full max-w-md rounded-[8px] border border-line bg-white p-6">
        <p className="text-sm font-semibold text-pine">Email verification</p>
        <h1 className="mt-3 text-2xl font-semibold">
          {isSupabaseConfigured() ? "Check your inbox" : "Authentication is not configured"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-ink/62">
          {isSupabaseConfigured()
            ? "Supabase has sent the sign-in link. Open it from the same browser to finish creating the portal session."
            : "This deployment does not currently have Supabase configured, so email-link verification cannot complete here yet."}
        </p>
        <div className="mt-6">
          <Link
            href="/login"
            className="inline-flex rounded-[8px] border border-line px-4 py-3 text-sm font-semibold hover:border-ink"
          >
            Back to login
          </Link>
        </div>
      </div>
    </main>
  );
}
