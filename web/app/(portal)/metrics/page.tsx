import {
  AutomationTrendChart,
  ResponseTimeChart,
  TopicPieChart,
} from "@/components/portal/charts";
import { EmptyState } from "@/components/portal/empty-state";
import { MetricCard } from "@/components/portal/metric-card";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import type { GovernanceLog, SessionSummary } from "@/services/api/types";
import { redirect } from "next/navigation";

function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

function questionText(session: SessionSummary) {
  return session.question ?? session.latestMessage ?? "";
}

function trendFromLogs(logs: GovernanceLog[]) {
  const counts = new Map<string, { day: string; answered: number; escalated: number }>();

  logs.forEach((log) => {
    const date = new Date(log.timestamp ?? "");
    const day = Number.isNaN(date.getTime())
      ? "Recent"
      : date.toLocaleDateString("en-US", { weekday: "short" });
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
    const question = questionText(session).toLowerCase();
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

function responseByHour(sessions: SessionSummary[]) {
  const buckets = new Map<string, { count: number; messages: number }>();

  sessions.forEach((session) => {
    const date = new Date(session.updatedAt ?? session.createdAt ?? "");
    const hour = Number.isNaN(date.getTime())
      ? "Recent"
      : date.toLocaleTimeString("en-US", { hour: "numeric" }).toLowerCase();
    const current = buckets.get(hour) ?? { count: 0, messages: 0 };
    current.count += 1;
    current.messages += session.messageCount ?? 1;
    buckets.set(hour, current);
  });

  return Array.from(buckets.entries()).map(([hour, value]) => ({
    hour,
    minutes: Number((value.messages / Math.max(value.count, 1)).toFixed(1)),
  }));
}

function kbGaps(sessions: SessionSummary[], logs: GovernanceLog[]) {
  const gapCounts = new Map<string, number>();

  sessions.forEach((session) => {
    const question = questionText(session);
    if (!question) {
      return;
    }
    const match = logs.find((log) => log.question === question && log.decision !== "answered");
    if (!match) {
      return;
    }
    const label =
      question.includes("?") ? question.slice(0, question.indexOf("?")) : question;
    gapCounts.set(label, (gapCounts.get(label) ?? 0) + 1);
  });

  return Array.from(gapCounts.entries()).slice(0, 3).map(([topic, count]) => ({
    topic,
    count,
    action: "Add approved knowledge or escalation guidance for this recurring ask.",
  }));
}

export default async function MetricsPage() {
  try {
    const api = await getServerApi();
    const [overview, metricsResponse, sessionsResponse, governanceResponse] = await Promise.all([
      api.getOverview(),
      api.getMetrics(),
      api.getSessions(),
      api.getGovernance(),
    ]);
    const hasDecisionData = metricsResponse.decisionCounts.total > 0;
    const hasSessionData = sessionsResponse.sessions.length > 0;
    const metrics = [
      {
        label: "Deflection rate",
        value: hasDecisionData ? percentage(metricsResponse.deflectionRate) : "\u2014",
        detail: "Share of answered sessions versus escalated ones.",
        trend: metricsResponse.decisionCounts.answered > 0 ? `${metricsResponse.decisionCounts.answered} answered` : null,
      },
      {
        label: "Human hours saved",
        value: hasDecisionData ? metricsResponse.humanHoursSaved.toFixed(1) : "\u2014",
        detail: "Estimated time saved from approved automated answers.",
        trend: metricsResponse.decisionCounts.escalated > 0 ? `${metricsResponse.decisionCounts.escalated} escalated` : null,
      },
      {
        label: "Active sessions",
        value: hasSessionData || overview.metrics.activeSessions > 0 ? String(overview.metrics.activeSessions) : "\u2014",
        detail: "Open customer conversations currently in the tenant queue.",
        trend: hasSessionData ? `${sessionsResponse.sessions.length} total tracked` : null,
      },
      {
        label: "Knowledge entries",
        value: overview.metrics.activeKnowledgeEntries > 0 ? String(overview.metrics.activeKnowledgeEntries) : "\u2014",
        detail: "Approved answers available to the automation layer.",
        trend: null,
      },
    ];
    const automationTrend = trendFromLogs(governanceResponse.logs);
    const topicDistribution = topicsFromSessions(sessionsResponse.sessions);
    const hourlyResponse = responseByHour(sessionsResponse.sessions);
    const gaps = kbGaps(sessionsResponse.sessions, governanceResponse.logs);
    const hasTrendData = automationTrend.some((item) => item.answered > 0 || item.escalated > 0);
    const hasTopicData = topicDistribution.length > 0;
    const hasHourlyData = hourlyResponse.length > 0;

    return (
      <>
        <PageHeader
          eyebrow="Metrics"
          title="Support performance without guesswork."
          copy="Track automation, escalation pressure, session volume, and the missing answers customers keep asking for."
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <Panel title="Automation trend" eyebrow="AI resolved vs human escalated">
            {hasTrendData ? (
              <AutomationTrendChart data={automationTrend} />
            ) : (
              <EmptyState
                title="No automation trend yet"
                copy="This chart will appear after the current tenant has live answered and escalated decisions."
              />
            )}
          </Panel>

          <Panel title="Topic distribution" eyebrow="Conversation mix">
            {hasTopicData ? (
              <>
                <TopicPieChart data={topicDistribution} />
              <div className="grid gap-2">
                {topicDistribution.map((topic) => (
                  <div key={topic.name} className="flex items-center justify-between rounded-[8px] bg-mist px-3 py-2 text-sm">
                    <span>{topic.name}</span>
                    <span className="font-semibold">{topic.value}%</span>
                  </div>
                ))}
              </div>
              </>
            ) : (
              <EmptyState
                title="No topic mix yet"
                copy="Topic distribution will fill in after live customer sessions are recorded for the current tenant."
              />
            )}
          </Panel>
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <Panel title="Response proxy by hour" eyebrow="Avg. messages per session">
            {hasHourlyData ? (
              <ResponseTimeChart data={hourlyResponse} />
            ) : (
              <EmptyState
                title="No response timing yet"
                copy="Response timing trends will appear after the first set of live conversations arrives for this tenant."
              />
            )}
          </Panel>

          <Panel title="KB gap insights" eyebrow="Questions without approved coverage">
            <div className="space-y-3">
              {gaps.length ? (
                gaps.map((gap) => (
                  <article key={gap.topic} className="rounded-[8px] border border-line p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3 className="font-semibold">{gap.topic}</h3>
                      <span className="rounded-[8px] bg-citron px-2.5 py-1 text-xs font-semibold text-ink">
                        {gap.count} asks
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-ink/66">{gap.action}</p>
                  </article>
                ))
              ) : sessionsResponse.sessions.length ? (
                <article className="rounded-[8px] border border-line p-4 text-sm leading-6 text-ink/66">
                  No recurring unanswered gaps were detected in the currently loaded session sample.
                </article>
              ) : (
                <EmptyState
                  title="No gap analysis yet"
                  copy="Once customer sessions accumulate, this panel will surface the repeated questions that still need approved knowledge or escalation guidance."
                />
              )}
            </div>
          </Panel>
        </div>
      </>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
