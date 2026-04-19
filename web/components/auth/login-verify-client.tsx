"use client";

import { useClerk } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

function VerificationPanel({
  title,
  copy,
  action,
}: {
  title: string;
  copy: string;
  action?: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper p-6 text-ink md:p-10">
      <div className="w-full max-w-md rounded-[8px] border border-line bg-white p-6">
        <p className="text-sm font-semibold text-pine">Email verification</p>
        <h1 className="mt-3 text-2xl font-semibold">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-ink/62">{copy}</p>
        <div className="mt-6">{action}</div>
      </div>
    </main>
  );
}

export function LoginVerifyClient() {
  const clerk = useClerk();
  const [isActivating, setIsActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isActivating) {
      return;
    }

    setIsActivating(true);

    const completeSignIn = (to = "/dashboard") => {
      window.location.assign(to);
      return Promise.resolve();
    };

    void clerk
      .handleEmailLinkVerification(
        {
          redirectUrlComplete: `${window.location.origin}/dashboard`,
          redirectUrl: `${window.location.origin}/login`,
        },
        completeSignIn,
      )
      .then(() => completeSignIn())
      .catch((verificationError: unknown) => {
        const message =
          verificationError instanceof Error
            ? verificationError.message
            : "The sign-in link could not be verified. Request a fresh link and try again.";
        setError(message);
        setIsActivating(false);
      });
  }, [clerk, isActivating]);

  if (error) {
    return (
      <VerificationPanel
        title="The sign-in link could not be verified"
        copy={error}
        action={
          <Link
            href="/login"
            className="inline-flex rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine"
          >
            Request a new link
          </Link>
        }
      />
    );
  }

  return (
    <VerificationPanel
      title="Signing you in"
      copy="Your email link was verified. SVMP CS is activating the portal session now."
    />
  );
}
