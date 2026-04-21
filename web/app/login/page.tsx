import { ClerkSignInPanel } from "@/components/auth/clerk-sign-in-panel";
import { PreviewLogin } from "@/components/auth/preview-login";
import { getAuthSafe } from "@/lib/clerk-auth";
import {
  authConfigurationIssue,
  isClerkConfigured,
  isUnsafePreviewAuthEnabled,
} from "@/lib/clerk-env";

const checks = [
  "Magic-link sign-in for invited users",
  "Google SSO verifies the user identity",
  "Tenant access resolved from Mongo verified users",
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
  const backendUnavailable = params.backend === "unavailable";
  const nextPath =
    typeof requestedNext === "string" && requestedNext.startsWith("/") && !requestedNext.startsWith("//")
      ? requestedNext
      : "/dashboard";

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
                ? "Use Google or your invited email. The backend checks MongoDB for your tenant, role, and permissions before returning any dashboard data."
                : previewEnabled
                  ? "Use the temporary built-in portal password. Tenant access is still resolved on the server before dashboard pages render."
                  : "Authentication is locked until the production auth environment is configured."}
            </p>

            {backendUnavailable ? (
              <div className="mt-4 rounded-[8px] border border-[#AA8A24]/20 bg-[#F8E7A6] p-4 text-sm leading-6 text-[#6D5613]">
                The dashboard is temporarily unavailable, so sign in starts here until the backend connection is restored.
              </div>
            ) : null}

            <div className="mt-8">
              {clerkConfigured ? (
                <ClerkSignInPanel />
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
