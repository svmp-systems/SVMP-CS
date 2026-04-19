import {
  AutomationTrendChart,
  ResponseTimeChart,
  TopicPieChart,
} from "@/components/portal/charts";
import { MetricCard } from "@/components/portal/metric-card";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { api } from "@/lib/api-client";
import { automationTrend, responseByHour, topicDistribution } from "@/lib/mock-data";

const gaps = [
  {
    topic: "Offer stacking",
    count: 18,
    action: "Add approved rule for combining promotions.",
  },
  {
    topic: "Engraving",
    count: 11,
    action: "Define availability, timing, and escalation rules.",
  },
  {
    topic: "Damaged delivery",
    count: 7,
    action: "Add replacement policy and photo request copy.",
  },
];

export default async function MetricsPage() {
  const { metrics } = await api.getOverview();

  return (
    <>
      <PageHeader
        eyebrow="Metrics"
        title="Support performance without guesswork."
        copy="Track automation, escalation pressure, response speed, topic mix, and the missing answers customers keep asking for."
        action={
          <select className="h-11 rounded-[8px] border border-line bg-white px-3 text-sm font-semibold outline-none focus:border-pine">
            <option>Last 7 days</option>
            <option>Last 30 days</option>
            <option>This quarter</option>
          </select>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric: any) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel title="Automation trend" eyebrow="AI resolved vs human escalated">
          <AutomationTrendChart data={automationTrend} />
        </Panel>

        <Panel title="Topic distribution" eyebrow="Conversation mix">
          <TopicPieChart data={topicDistribution} />
          <div className="grid gap-2">
            {topicDistribution.map((topic) => (
              <div key={topic.name} className="flex items-center justify-between rounded-[8px] bg-mist px-3 py-2 text-sm">
                <span>{topic.name}</span>
                <span className="font-semibold">{topic.value}%</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Panel title="Response time by hour" eyebrow="Median minutes">
          <ResponseTimeChart data={responseByHour} />
        </Panel>

        <Panel title="KB gap insights" eyebrow="Questions without coverage">
          <div className="space-y-3">
            {gaps.map((gap) => (
              <article key={gap.topic} className="rounded-[8px] border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold">{gap.topic}</h3>
                  <span className="rounded-[8px] bg-citron px-2.5 py-1 text-xs font-semibold text-ink">
                    {gap.count} asks
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-ink/66">{gap.action}</p>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
