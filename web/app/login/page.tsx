import { MagicLinkSignIn } from "@/components/auth/magic-link-sign-in";
import { PreviewLogin } from "@/components/auth/preview-login";
import { getAuthSafe } from "@/lib/clerk-auth";
import {
  authConfigurationIssue,
  isClerkConfigured,
  isUnsafePreviewAuthEnabled,
} from "@/lib/clerk-env";
import { redirect } from "next/navigation";

const checks = [
  "Magic-link sign-in for invited users",
  "Google SSO can layer in later for team workspaces",
  "Tenant access resolved by backend session",
  "Inactive subscriptions routed to billing only",
];

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const clerkConfigured = isClerkConfigured();
  const previewEnabled = isUnsafePreviewAuthEnabled();
  const configurationIssue = authConfigurationIssue();
  const { userId } = clerkConfigured ? await getAuthSafe() : { userId: null };
  const params = await searchParams;
  const requestedNext = params.next;
  const organizationState = params.organization;
  const organizationRequired =
    organizationState === "required" ||
    (Array.isArray(organizationState) && organizationState.includes("required"));
  const nextPath =
    typeof requestedNext === "string" && requestedNext.startsWith("/") && !requestedNext.startsWith("//")
      ? requestedNext
      : "/dashboard";

  if (userId) {
    redirect("/dashboard");
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
              Paid client access is tied to a verified user record. SVMP CS resolves the tenant on the backend and gates operational pages by subscription state.
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
              {clerkConfigured
                ? "Use your invited work email and SVMP CS will send a secure sign-in link for this browser."
                : previewEnabled
                  ? "Use the temporary built-in portal password. Tenant access is still resolved on the server before dashboard pages render."
                  : "Authentication is locked until the production auth environment is configured."}
            </p>

            <div className="mt-8">
              {clerkConfigured ? (
                <MagicLinkSignIn organizationRequired={organizationRequired} />
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
