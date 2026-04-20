"use client";

import { useClerk, useSignIn } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Notice } from "@/components/portal/notice";

function errorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "errors" in error && Array.isArray(error.errors)) {
    const firstError = error.errors[0];
    if (firstError && typeof firstError === "object" && "longMessage" in firstError) {
      return String(firstError.longMessage);
    }
    if (firstError && typeof firstError === "object" && "message" in firstError) {
      return String(firstError.message);
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

export function MagicLinkSignIn() {
  const router = useRouter();
  const { setActive } = useClerk();
  const { signIn, fetchStatus } = useSignIn();
  const [email, setEmail] = useState("");
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isAwaitingVerification, setIsAwaitingVerification] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!isAwaitingVerification || !signIn?.emailLink.verification?.createdSessionId) {
      return;
    }

    if (signIn.emailLink.verification.status !== "verified") {
      return;
    }

    let cancelled = false;

    void setActive?.({ session: signIn.emailLink.verification.createdSessionId }).then(() => {
      if (!cancelled) {
        router.replace("/dashboard");
      }
    });

    return () => {
      cancelled = true;
    };
  }, [isAwaitingVerification, router, setActive, signIn]);

  async function sendMagicLink() {
    if (!signIn) {
      return;
    }

    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      setFeedback({ tone: "error", text: "Enter the invited email for your SVMP portal access." });
      return;
    }

    setIsSending(true);
    setFeedback(null);

    try {
      const verificationUrl =
        typeof window === "undefined"
          ? "/login/verify"
          : `${window.location.origin}/login/verify`;

      const { error } = await signIn.emailLink.sendLink({
        emailAddress: normalizedEmail,
        verificationUrl,
      });

      if (error) {
        throw error;
      }

      setSubmittedEmail(normalizedEmail);
      setIsAwaitingVerification(true);
      setFeedback({
        tone: "success",
        text: `A secure sign-in link was sent to ${normalizedEmail}. Open it on this browser to continue into the portal.`,
      });

      const verificationResult = await signIn.emailLink.waitForVerification();

      if (verificationResult.error) {
        throw verificationResult.error;
      }

      const verification = signIn.emailLink.verification;
      if (verification?.status === "verified" && verification.createdSessionId) {
        await setActive?.({ session: verification.createdSessionId });
        router.replace("/dashboard");
      }
    } catch (error) {
      setIsAwaitingVerification(false);
      setFeedback({
        tone: "error",
        text: errorMessage(error, "Unable to send a magic link right now."),
      });
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="space-y-6">
      {feedback ? (
        <Notice
          title={feedback.tone === "success" ? "Check your inbox" : "Sign-in issue"}
          copy={feedback.text}
          tone={feedback.tone}
        />
      ) : null}

      <div className="space-y-4">
        <label className="grid gap-2">
          <span className="text-sm font-semibold">Work email</span>
          <input
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            className="h-12 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={isSending}
          />
        </label>

        <button
          type="button"
          className="w-full rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => void sendMagicLink()}
          disabled={!signIn || fetchStatus === "fetching" || isSending}
        >
          {isSending ? "Sending link..." : "Email me a sign-in link"}
        </button>
      </div>

      <div className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
        <p className="font-semibold text-ink">How this works</p>
        <p className="mt-2">
          Use the invited email for your tenant. The browser never chooses a tenant manually;
          access is resolved from your MongoDB verified user record on the backend.
        </p>
        {submittedEmail ? (
          <p className="mt-2">
            Waiting for verification on <span className="font-semibold text-ink">{submittedEmail}</span>.
          </p>
        ) : null}
      </div>

      <p className="text-sm leading-6 text-ink/62">
        Need a new invite or a different tenant? Continue with{" "}
        <Link href="/signup" className="font-semibold text-ink">
          invitation access
        </Link>
        .
      </p>
    </div>
  );
}
