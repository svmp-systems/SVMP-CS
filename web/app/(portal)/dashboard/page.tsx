import { AutomationTrendChart, TopicPieChart } from "@/components/portal/charts";
import { MetricCard } from "@/components/portal/metric-card";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";
import { automationTrend, governanceLogs, topicDistribution } from "@/lib/mock-data";
import Link from "next/link";

export default async function DashboardPage() {
  const [{ metrics }, { sessions }] = await Promise.all([api.getOverview(), api.getSessions()]);
  const recentSessions = sessions.slice(0, 3);

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Is SVMP helping support today?"
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
        {metrics.map((metric: any) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <Panel title="AI resolved vs human escalated" eyebrow="Automation trend">
          <AutomationTrendChart data={automationTrend} />
        </Panel>
        <Panel title="Topic distribution" eyebrow="This week">
          <TopicPieChart data={topicDistribution} />
          <div className="grid gap-2">
            {topicDistribution.map((topic) => (
              <div key={topic.name} className="flex items-center justify-between text-sm">
                <span className="text-ink/68">{topic.name}</span>
                <span className="font-semibold">{topic.value}%</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <Panel title="Recent activity" eyebrow="Latest conversations">
          <div className="space-y-3">
            {recentSessions.map((session) => (
              <Link
                key={session.id ?? session._id}
                href={`/sessions/${session.id ?? session._id}`}
                className="block rounded-[8px] border border-line p-4 hover:border-ink"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold">{session.question ?? session.latestMessage ?? "Customer conversation"}</p>
                  <StatusBadge tone={statusTone(session.status ?? session.dashboardStatus ?? "pending")}>{session.status ?? session.dashboardStatus ?? "pending"}</StatusBadge>
                </div>
                <p className="mt-2 text-sm text-ink/60">{session.customer ?? session.userId ?? "Customer"} - {session.timestamp ?? session.updatedAt ?? "Latest"}</p>
              </Link>
            ))}
          </div>
        </Panel>

        <Panel title="System health" eyebrow="Live checks">
          <div className="space-y-3">
            {[
              ["Subscription", "active"],
              ["WhatsApp webhook", "healthy"],
              ["Knowledge base", "ready"],
              ["Escalation policy", "ready"],
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
        <div className="grid gap-3 md:grid-cols-3">
          {[
            "Review engraving and offer-stacking policy.",
            "Add support handoff destination for escalations.",
            `Investigate ${governanceLogs.length} recent governance events.`,
          ].map((warning) => (
            <div key={warning} className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/70">
              {warning}
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}
