import { PreviewLogin } from "@/components/auth/preview-login";
import { SupabaseAuthPanel } from "@/components/auth/supabase-auth-panel";
import { authConfigurationIssue, isSupabaseConfigured, isUnsafePreviewAuthEnabled } from "@/lib/portal-auth-env";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

const checks = [
  "Google sign-in through Supabase Auth",
  "Magic-link access for invited users",
  "Tenant membership resolved from Supabase-backed portal access records",
  "Inactive subscriptions routed to billing only",
];

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const supabaseConfigured = isSupabaseConfigured();
  const previewEnabled = isUnsafePreviewAuthEnabled();
  const configurationIssue = authConfigurationIssue();
  const params = await searchParams;
  const requestedNext = params.next;
  const nextPath =
    typeof requestedNext === "string" && requestedNext.startsWith("/") && !requestedNext.startsWith("//")
      ? requestedNext
      : "/dashboard";

  if (supabaseConfigured) {
    const supabase = await createServerSupabaseClient();
    const { data } = await supabase.auth.getClaims();
    if (data?.claims?.sub) {
      redirect("/dashboard");
    }
  }

  return (
    <main className="min-h-screen bg-paper text-ink">
      <div className="grid min-h-screen lg:grid-cols-[0.95fr_1.05fr]">
        <section className="flex flex-col justify-between border-b border-line p-6 md:p-10 lg:border-b-0 lg:border-r">
          <a href="/" className="text-lg font-semibold">
            SVMP CS
          </a>
          <div className="my-16 max-w-xl">
            <p className="text-sm font-semibold text-pine">Customer portal</p>
            <h1 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              Sign in to manage your AI support system.
            </h1>
            <p className="mt-7 text-lg leading-8 text-ink/68">
              Production access runs through Supabase Auth. The backend resolves the tenant membership, role, and
              subscription state before any operational dashboard data is returned.
            </p>
          </div>
          <div className="grid gap-px overflow-hidden rounded-[8px] border border-line bg-line">
            {checks.map((item) => (
              <div key={item} className="bg-white p-4 text-sm font-semibold text-ink/72">
                {item}
              </div>
            ))}
          </div>
        </section>

        <section className="flex items-center justify-center p-6 md:p-10">
          <div className="w-full max-w-md rounded-[8px] border border-line bg-white p-6">
            <p className="text-sm font-semibold text-pine">Portal access</p>
            <h2 className="mt-3 text-2xl font-semibold">Welcome back</h2>
            <p className="mt-3 text-sm leading-6 text-ink/62">
              {supabaseConfigured
                ? "Use Google or your work email. Supabase authenticates the user, and the backend decides which tenant and role that session is allowed to access."
                : previewEnabled
                  ? "Use the temporary built-in portal password. Tenant access is still resolved on the server before dashboard pages render."
                  : "Authentication is locked until the production auth environment is configured."}
            </p>

            <div className="mt-8">
              {supabaseConfigured ? (
                <SupabaseAuthPanel nextPath={nextPath} />
              ) : previewEnabled ? (
                <PreviewLogin nextPath={nextPath} />
              ) : (
                <div className="rounded-[8px] border border-rose/30 bg-rose/10 p-4 text-sm leading-6 text-rose">
                  {configurationIssue}
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
