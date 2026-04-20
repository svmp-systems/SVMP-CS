import { AutomationTrendChart, TopicPieChart } from "@/components/portal/charts";
import { EmptyState } from "@/components/portal/empty-state";
import { Notice } from "@/components/portal/notice";
import { MetricCard } from "@/components/portal/metric-card";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import type { GovernanceLog, SessionSummary } from "@/services/api/types";
import Link from "next/link";
import { redirect } from "next/navigation";

function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

function sessionQuestion(session: SessionSummary) {
  return session.question ?? session.latestMessage ?? "Customer conversation";
}

function sessionCustomer(session: SessionSummary) {
  return session.customer ?? session.userId ?? session.clientId ?? "Customer";
}

function sessionStatus(session: SessionSummary) {
  return session.dashboardStatus ?? session.status ?? "pending";
}

function timeLabel(value?: string | null) {
  if (!value) {
    return "Live";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function trendFromLogs(logs: GovernanceLog[]) {
  const counts = new Map<string, { day: string; answered: number; escalated: number }>();

  logs.forEach((log) => {
    const day = timeLabel(log.timestamp).split(",")[0] || "Recent";
    const current = counts.get(day) ?? { day, answered: 0, escalated: 0 };
    if (log.decision === "answered") {
      current.answered += 1;
    }
    if (log.decision === "escalated") {
      current.escalated += 1;
    }
    counts.set(day, current);
  });

  return Array.from(counts.values()).slice(-7);
}

function topicsFromSessions(sessions: SessionSummary[]) {
  const buckets = new Map<string, number>();

  sessions.forEach((session) => {
    const question = sessionQuestion(session).toLowerCase();
    const topic =
      question.includes("ship")
        ? "Shipping"
        : question.includes("return")
          ? "Returns"
          : question.includes("offer") || question.includes("price")
            ? "Pricing"
            : question.includes("stock") || question.includes("available")
              ? "Stock"
              : "General";
    buckets.set(topic, (buckets.get(topic) ?? 0) + 1);
  });

  const total = sessions.length || 1;
  return Array.from(buckets.entries()).map(([name, count]) => ({
    name,
    value: Math.round((count / total) * 100),
  }));
}

export default async function DashboardPage() {
  try {
    const api = await getServerApi();
    const [overview, sessionsResponse, integrationsResponse] = await Promise.all([
      api.getOverview(),
      api.getSessions(),
      api.getIntegrations(),
    ]);
    const recentSessions = sessionsResponse.sessions.slice(0, 3);
    const automationTrend = trendFromLogs(overview.recentActivity);
    const topicDistribution = topicsFromSessions(sessionsResponse.sessions);
    const hasDecisionData = overview.metrics.aiResolved + overview.metrics.humanEscalated > 0;
    const hasSessionData = sessionsResponse.sessions.length > 0;
    const hasTrendData = automationTrend.some((item) => item.answered > 0 || item.escalated > 0);
    const hasTopicData = topicDistribution.length > 0;
    const metrics = [
      {
        label: "Deflection rate",
        value: hasDecisionData ? percentage(overview.metrics.deflectionRate) : "\u2014",
        detail: "Questions answered without a human handoff.",
        trend: overview.metrics.aiResolved > 0 ? `${overview.metrics.aiResolved} answered` : null,
      },
      {
        label: "Human hours saved",
        value: hasDecisionData ? overview.metrics.humanHoursSaved.toFixed(1) : "\u2014",
        detail: "Estimated support time saved from automated answers.",
        trend: overview.metrics.humanEscalated > 0 ? `${overview.metrics.humanEscalated} escalated` : null,
      },
      {
        label: "Active sessions",
        value: hasSessionData || overview.metrics.activeSessions > 0 ? String(overview.metrics.activeSessions) : "\u2014",
        detail: "Open customer conversations across the resolved tenant.",
        trend: overview.metrics.activeKnowledgeEntries > 0 ? `${overview.metrics.activeKnowledgeEntries} KB entries` : null,
      },
      {
        label: "Safety score",
        value: overview.metrics.safetyScore === null ? "\u2014" : String(overview.metrics.safetyScore),
        detail: "Governance scoring across the latest answered and escalated decisions.",
        trend: null,
      },
    ];
    const whatsapp = integrationsResponse.integrations.find((integration) => integration.provider === "whatsapp");

    return (
      <>
        <PageHeader
          eyebrow="Overview"
          title="Is SVMP CS helping support today?"
          copy="Monitor live value, health, and anything that needs setup attention before customers feel it."
          action={
            <Link
              href="/knowledge-base"
              className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine"
            >
              Test knowledge
            </Link>
          }
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
          <Panel title="AI resolved vs human escalated" eyebrow="Automation trend">
            {hasTrendData ? (
              <AutomationTrendChart data={automationTrend} />
            ) : (
              <EmptyState
                title="No automation trend yet"
                copy="This chart will fill in after live answered and escalated decisions start landing for the current tenant."
              />
            )}
          </Panel>
          <Panel title="Topic distribution" eyebrow="Recent session mix">
            {hasTopicData ? (
              <>
                <TopicPieChart data={topicDistribution} />
                <div className="grid gap-2">
                  {topicDistribution.map((topic) => (
                    <div key={topic.name} className="flex items-center justify-between text-sm">
                      <span className="text-ink/68">{topic.name}</span>
                      <span className="font-semibold">{topic.value}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState
                title="No topic mix yet"
                copy="Topic distribution will appear once the current tenant has recorded live customer sessions."
              />
            )}
          </Panel>
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_0.9fr]">
          <Panel title="Recent activity" eyebrow="Latest conversations">
            {recentSessions.length ? (
              <div className="space-y-3">
                {recentSessions.map((session) => {
                  const status = sessionStatus(session);
                  return (
                    <Link
                      key={session.id}
                      href={`/sessions/${session.id}`}
                      className="block rounded-[8px] border border-line p-4 hover:border-ink"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-semibold">{sessionQuestion(session)}</p>
                        <StatusBadge tone={statusTone(status)}>{status}</StatusBadge>
                      </div>
                      <p className="mt-2 text-sm text-ink/60">
                        {sessionCustomer(session)} - {timeLabel(session.updatedAt ?? session.createdAt)}
                      </p>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No recent conversations yet"
                copy="Once WhatsApp or another approved channel starts sending tenant traffic, the latest customer threads will surface here."
              />
            )}
          </Panel>

          <Panel title="System health" eyebrow="Live checks">
            <div className="space-y-3">
              {[
                ["Subscription", overview.systemHealth.subscription],
                ["WhatsApp webhook", whatsapp?.health ?? "unknown"],
                ["Knowledge base", overview.metrics.activeKnowledgeEntries > 0 ? "ready" : "warning"],
                ["Escalation policy", overview.setupWarnings.length ? "warning" : "ready"],
              ].map(([label, status]) => (
                <div key={label} className="flex items-center justify-between rounded-[8px] border border-line p-4">
                  <span className="font-semibold">{label}</span>
                  <StatusBadge tone={statusTone(status)}>{status}</StatusBadge>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel title="Setup warnings" eyebrow="Needs attention" className="mt-6">
          {overview.setupWarnings.length ? (
            <div className="grid gap-3 md:grid-cols-3">
              {overview.setupWarnings.map((warning) => (
                <div key={warning} className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/70">
                  {warning}
                </div>
              ))}
            </div>
          ) : (
            <Notice
              title="No active setup warnings"
              copy="The resolved tenant is currently clear of onboarding and configuration blockers."
              tone="success"
            />
          )}
        </Panel>
      </>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
