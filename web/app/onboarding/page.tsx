import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { Notice } from "@/components/portal/notice";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { tenantDisplayName } from "@/lib/tenant-display";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

function onboardingSteps({
  tenantName,
  brandVoiceReady,
  knowledgeCount,
  whatsappReady,
  testQuestionReady,
  activeSubscription,
}: {
  tenantName: string;
  brandVoiceReady: boolean;
  knowledgeCount: number;
  whatsappReady: boolean;
  testQuestionReady: boolean;
  activeSubscription: boolean;
}) {
  return [
    {
      title: "Business profile",
      copy: `${tenantName} profile, website, industry, and support email are saved.`,
      done: Boolean(tenantName),
      href: "/settings",
    },
    {
      title: "Brand voice",
      copy: brandVoiceReady
        ? "Tone, use words, avoid words, and escalation style are configured."
        : "Define tone, vocabulary, and escalation style before letting the AI reply.",
      done: brandVoiceReady,
      href: "/brand-voice",
    },
    {
      title: "Knowledge base",
      copy:
        knowledgeCount > 0
          ? `${knowledgeCount} approved FAQ entries are ready for customer questions.`
          : "Add approved FAQs before enabling automated answers.",
      done: knowledgeCount > 0,
      href: "/knowledge-base",
    },
    {
      title: "WhatsApp integration",
      copy: whatsappReady
        ? "WhatsApp status is healthy enough for production traffic."
        : "Confirm webhook health and status before going live.",
      done: whatsappReady,
      href: "/integrations",
    },
    {
      title: "Test SVMP CS",
      copy: testQuestionReady
        ? "Dry-run knowledge checks are available for this tenant."
        : "Run a test question once knowledge and threshold settings are ready.",
      done: testQuestionReady,
      href: "/knowledge-base",
    },
    {
      title: "Go live",
      copy: activeSubscription
        ? "Subscription access is active. Finish the remaining checks, then launch confidently."
        : "Billing must be active before the operational portal fully opens.",
      done: activeSubscription && brandVoiceReady && knowledgeCount > 0 && whatsappReady,
      href: "/settings",
    },
  ];
}

export default async function OnboardingPage() {
  try {
    const api = await getServerApi();
    const [me, tenant, brandVoiceResponse, knowledgeBase, integrations] = await Promise.all([
      api.getMe(),
      api.getTenant(),
      api.getBrandVoice(),
      api.getKnowledgeBase({ active: true }),
      api.getIntegrations(),
    ]);
    const whatsapp = integrations.integrations.find((integration) => integration.provider === "whatsapp");
    const brandVoice = brandVoiceResponse.brandVoice;
    const brandVoiceReady = Boolean(
      brandVoice.tone || brandVoice.escalationStyle || (brandVoice.use && brandVoice.use.length),
    );
    const knowledgeCount = knowledgeBase.entries.length;
    const whatsappReady = ["connected", "healthy", "active"].includes(whatsapp?.status ?? "");
    const displayName = tenantDisplayName(me, tenant) ?? "\u2014";
    const steps = onboardingSteps({
      tenantName: displayName,
      brandVoiceReady,
      knowledgeCount,
      whatsappReady,
      testQuestionReady: knowledgeCount > 0,
      activeSubscription: me.hasActiveSubscription,
    });
    const completed = steps.filter((step) => step.done).length;
    const progress = `${Math.round((completed / steps.length) * 100)}%`;

    return (
      <main className="min-h-screen bg-paper text-ink">
        <header className="border-b border-line bg-white px-5 py-4 md:px-8">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <Link href="/" className="font-semibold">
              SVMP CS
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
              This path is derived from the live tenant profile, approved knowledge, integration status, and subscription access already present in the backend.
            </p>
            <div className="mt-8 rounded-[8px] border border-line bg-white p-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold">Progress</p>
                <StatusBadge tone={statusTone(me.subscriptionStatus)}>{me.subscriptionStatus}</StatusBadge>
              </div>
              <div className="mt-4 h-3 overflow-hidden rounded-[8px] bg-mist">
                <div className="h-full bg-pine" style={{ width: progress }} />
              </div>
              <p className="mt-3 text-sm text-ink/62">
                {completed} of {steps.length} steps complete
              </p>
            </div>

            {!me.hasActiveSubscription ? (
              <div className="mt-6">
                <Notice
                  title="Billing still blocks launch"
                  copy="The onboarding checklist can continue, but only billing stays fully open until this tenant has an active or trialing subscription."
                  tone="warning"
                />
              </div>
            ) : null}
          </section>

          <section className="rounded-[8px] border border-line bg-white">
            <div className="border-b border-line p-5">
              <h2 className="text-xl font-semibold">{displayName} onboarding</h2>
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
                      <Link href={step.href} className="mt-3 inline-flex text-sm font-semibold text-pine hover:text-ink">
                        Open step
                      </Link>
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
  } catch (error) {
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
