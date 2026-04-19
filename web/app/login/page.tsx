import Link from "next/link";
import { SignIn } from "@clerk/nextjs";

const checks = [
  "Google login for team members",
  "Email fallback for invited users",
  "Tenant access resolved by backend session",
  "Inactive subscriptions routed to billing only",
];

export default function LoginPage() {
  return (
    <main className="min-h-screen bg-paper text-ink">
      <div className="grid min-h-screen lg:grid-cols-[0.95fr_1.05fr]">
        <section className="flex flex-col justify-between border-b border-line p-6 md:p-10 lg:border-b-0 lg:border-r">
          <Link href="/" className="text-lg font-semibold">
            SVMP
          </Link>
          <div className="my-16 max-w-xl">
            <p className="text-sm font-semibold text-pine">Customer portal</p>
            <h1 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              Sign in to manage your AI support system.
            </h1>
            <p className="mt-7 text-lg leading-8 text-ink/68">
              Paid client access is tied to your organization. SVMP resolves the tenant on the backend and gates operational pages by subscription state.
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
            <p className="text-sm font-semibold text-pine">Stay Parfums</p>
            <h2 className="mt-3 text-2xl font-semibold">Welcome back</h2>
            <p className="mt-3 text-sm leading-6 text-ink/62">
              Use Google for the fastest access, or continue with email if your team invite was sent there.
            </p>

            <div className="mt-8">
              <SignIn
                routing="path"
                path="/login"
                forceRedirectUrl="/dashboard"
                signUpUrl="/login"
                appearance={{
                  elements: {
                    rootBox: "w-full",
                    cardBox: "shadow-none border-0 w-full",
                    card: "shadow-none border-0 p-0 w-full",
                    headerTitle: "hidden",
                    headerSubtitle: "hidden",
                    socialButtonsBlockButton:
                      "rounded-[8px] border-line text-sm font-semibold",
                    formButtonPrimary:
                      "rounded-[8px] bg-ink text-paper text-sm font-semibold hover:bg-pine",
                    footer: "hidden",
                  },
                }}
              />
            </div>

            <p className="mt-6 text-xs leading-5 text-ink/54">
              Google and email access are controlled in Clerk. Users need an active organization mapped to an SVMP tenant.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
