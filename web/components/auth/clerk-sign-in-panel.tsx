"use client";

import { SignIn } from "@clerk/nextjs";

export function ClerkSignInPanel() {
  return (
    <SignIn
      routing="hash"
      forceRedirectUrl="/dashboard"
      signUpUrl="/signup"
      appearance={{
        elements: {
          rootBox: "w-full",
          card: "shadow-none border-0 p-0 bg-transparent",
          header: "hidden",
          footer: "hidden",
          formButtonPrimary:
            "rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine",
          socialButtonsBlockButton:
            "rounded-[8px] border border-line px-4 py-3 text-sm font-semibold hover:border-ink",
          formFieldInput:
            "h-12 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine",
          dividerLine: "bg-line",
          dividerText: "text-ink/50",
        },
      }}
    />
  );
}
