import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";
import { auditEvents } from "@/lib/mock-data";

function formatScore(score: number | null) {
  return score === null ? "n/a" : score.toFixed(2);
}

export default async function GovernancePage() {
  const { logs } = await api.getGovernance();
  const escalated = logs.filter((log) => log.decision === "escalated").length;
  const blocked = logs.filter((log) => log.decision === "blocked").length;
  const answered = logs.filter((log) => log.decision === "answered").length;

  return (
    <>
      <PageHeader
        eyebrow="Governance"
        title="Every answer has a reason."
        copy="Review escalations, low-confidence matches, blocked responses, source usage, and the scores behind each decision."
        action={
          <button className="rounded-[8px] border border-line bg-white px-4 py-3 text-sm font-semibold hover:border-ink">
            Export logs
          </button>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        {[
          ["Answered", answered, "Knowledge matched and safety passed."],
          ["Escalated", escalated, "A human should review before replying."],
          ["Blocked", blocked, "Unsafe or overreaching reply prevented."],
        ].map(([label, value, detail]) => (
          <article key={label} className="rounded-[8px] border border-line bg-white p-5">
            <p className="text-sm font-semibold text-ink/62">{label}</p>
            <p className="mt-4 font-serif text-4xl leading-none">{value}</p>
            <p className="mt-4 text-sm leading-6 text-ink/62">{detail}</p>
          </article>
        ))}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <Panel title="Decision log" eyebrow={`${logs.length} recent events`}>
          <div className="space-y-3">
            {logs.map((log) => (
              <article key={log.id} className="rounded-[8px] border border-line p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm text-ink/56">{log.timestamp}</p>
                    <h3 className="mt-2 text-lg font-semibold">{log.question}</h3>
                  </div>
                  <StatusBadge tone={statusTone(log.decision)}>{log.decision}</StatusBadge>
                </div>
                <p className="mt-3 text-sm leading-6 text-ink/68">{log.reason}</p>
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
                  <div className="rounded-[8px] bg-mist p-3">
                    <p className="text-ink/52">Source</p>
                    <p className="mt-1 font-semibold">{log.source ?? "None"}</p>
                  </div>
                  <div className="rounded-[8px] bg-mist p-3">
                    <p className="text-ink/52">Similarity</p>
                    <p className="mt-1 font-semibold">{formatScore(log.similarity)}</p>
                  </div>
                  <div className="rounded-[8px] bg-mist p-3">
                    <p className="text-ink/52">Groundedness</p>
                    <p className="mt-1 font-semibold">{formatScore(log.groundedness)}</p>
                  </div>
                  <div className="rounded-[8px] bg-mist p-3">
                    <p className="text-ink/52">Safety</p>
                    <p className="mt-1 font-semibold">{formatScore(log.safety)}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Needs review" eyebrow="Trust queue">
            <div className="space-y-3">
              {logs
                .filter((log) => log.decision !== "answered")
                .map((log) => (
                  <div key={log.id} className="rounded-[8px] border border-line bg-paper p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold">{log.decision}</p>
                      <StatusBadge tone={statusTone(log.decision)}>{formatScore(log.groundedness)}</StatusBadge>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-ink/66">{log.reason}</p>
                  </div>
                ))}
            </div>
          </Panel>

          <Panel title="Audit activity" eyebrow="Configuration changes">
            <div className="space-y-3">
              {auditEvents.map((event) => (
                <div key={`${event.action}-${event.timestamp}`} className="rounded-[8px] border border-line p-4">
                  <p className="text-sm font-semibold">{event.action}</p>
                  <p className="mt-2 text-sm leading-6 text-ink/64">{event.detail}</p>
                  <p className="mt-3 text-xs text-ink/52">
                    {event.actor} - {event.timestamp}
                  </p>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
