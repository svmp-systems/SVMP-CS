import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";

const steps = [
  {
    title: "Business profile",
    copy: "Company name, website, industry, and support email.",
    done: true,
  },
  {
    title: "Brand voice",
    copy: "Tone, words to use, words to avoid, and escalation style.",
    done: true,
  },
  {
    title: "Knowledge base",
    copy: "Add FAQs, import CSV, paste docs, or seed from website content.",
    done: true,
  },
  {
    title: "WhatsApp integration",
    copy: "Connect Meta or Twilio and verify webhook health.",
    done: false,
  },
  {
    title: "Test SVMP",
    copy: "Ask sample customer questions before going live.",
    done: false,
  },
  {
    title: "Go live",
    copy: "Confirm safety threshold, handoff destination, and monitoring.",
    done: false,
  },
];

export default function OnboardingPage() {
  return (
    <main className="min-h-screen bg-paper text-ink">
      <header className="border-b border-line bg-white px-5 py-4 md:px-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <Link href="/" className="font-semibold">
            SVMP
          </Link>
          <Link
            href="/dashboard"
            className="rounded-[8px] border border-line px-4 py-2 text-sm font-semibold hover:border-ink"
          >
            Skip to dashboard
          </Link>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-8 px-5 py-10 md:px-8 lg:grid-cols-[0.75fr_1.25fr]">
        <section>
          <p className="text-sm font-semibold text-pine">Setup wizard</p>
          <h1 className="mt-4 font-serif text-5xl leading-tight">
            Take the tenant from paid to live.
          </h1>
          <p className="mt-6 text-base leading-7 text-ink/64">
            This is the guided path a business follows after payment. Each step maps to tenant settings, knowledge, integration status, and safety checks in the backend.
          </p>
          <div className="mt-8 rounded-[8px] border border-line bg-white p-5">
            <p className="text-sm font-semibold">Progress</p>
            <div className="mt-4 h-3 overflow-hidden rounded-[8px] bg-mist">
              <div className="h-full w-1/2 bg-pine" />
            </div>
            <p className="mt-3 text-sm text-ink/62">3 of 6 steps complete</p>
          </div>
        </section>

        <section className="rounded-[8px] border border-line bg-white">
          <div className="border-b border-line p-5">
            <h2 className="text-xl font-semibold">Stay Parfums onboarding</h2>
            <p className="mt-2 text-sm text-ink/62">Complete the remaining checks before turning on auto-answering.</p>
          </div>
          <div className="divide-y divide-line">
            {steps.map((step) => {
              const Icon = step.done ? CheckCircle2 : Circle;
              return (
                <article key={step.title} className="grid gap-4 p-5 sm:grid-cols-[2rem_1fr_auto] sm:items-start">
                  <Icon className={step.done ? "text-pine" : "text-ink/32"} size={22} />
                  <div>
                    <h3 className="font-semibold">{step.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-ink/62">{step.copy}</p>
                  </div>
                  <span className="rounded-[8px] border border-line px-3 py-1.5 text-xs font-semibold text-ink/62">
                    {step.done ? "Done" : "Next"}
                  </span>
                </article>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
