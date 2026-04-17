import Link from "next/link";

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

            <div className="mt-8 space-y-3">
              <Link
                href="/dashboard"
                className="flex w-full items-center justify-center rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine"
              >
                Continue with Google
              </Link>
              <form className="space-y-3">
                <label className="block text-sm font-semibold" htmlFor="email">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  placeholder="owner@stayparfums.com"
                  className="h-12 w-full rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                />
                <Link
                  href="/dashboard"
                  className="flex w-full items-center justify-center rounded-[8px] border border-line px-4 py-3 text-sm font-semibold hover:border-ink"
                >
                  Send magic link
                </Link>
              </form>
            </div>

            <p className="mt-6 text-xs leading-5 text-ink/54">
              Production login will use Clerk. This screen is ready for Clerk buttons and protected route redirects.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
