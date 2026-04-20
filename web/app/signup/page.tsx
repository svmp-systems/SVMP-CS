import { SignUp } from "@clerk/nextjs";
import { getAuthSafe } from "@/lib/clerk-auth";
import { isClerkConfigured } from "@/lib/clerk-env";
import { redirect } from "next/navigation";

export default async function SignUpPage() {
  const { userId } = await getAuthSafe();
  const clerkConfigured = isClerkConfigured();

  if (userId) {
    redirect("/dashboard");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper p-6 text-ink md:p-10">
      <div className="w-full max-w-md rounded-[8px] border border-line bg-white p-6">
        <p className="text-sm font-semibold text-pine">Invitation access</p>
        <h1 className="mt-3 text-2xl font-semibold">Join your SVMP CS workspace</h1>
        <p className="mt-3 text-sm leading-6 text-ink/62">
          Finish sign-up with the invited work email. Once the account is created, the backend checks MongoDB for your tenant, role, and permissions.
        </p>
        <div className="mt-8">
          {clerkConfigured ? (
            <SignUp
              routing="hash"
              forceRedirectUrl="/dashboard"
              signInUrl="/login"
              appearance={{
                elements: {
                  rootBox: "w-full",
                  card: "shadow-none border-0 p-0",
                  header: "hidden",
                  formButtonPrimary:
                    "rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine",
                  socialButtonsBlockButton:
                    "rounded-[8px] border border-line px-4 py-3 text-sm font-semibold hover:border-ink",
                  formFieldInput:
                    "h-12 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine",
                },
              }}
            />
          ) : (
            <div className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
              Invitation sign-up is unavailable until Clerk is configured in the live environment.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
