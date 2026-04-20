import { EmptyState } from "@/components/portal/empty-state";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import type { GovernanceLog } from "@/services/api/types";
import { redirect } from "next/navigation";

function formatScore(score: number | null) {
  return score === null ? "n/a" : score.toFixed(2);
}

export default async function GovernancePage() {
  try {
    const api = await getServerApi();
    const { logs } = await api.getGovernance();
    const escalated = logs.filter((log) => log.decision === "escalated").length;
    const blocked = logs.filter((log) => log.decision === "blocked").length;
    const answered = logs.filter((log) => log.decision === "answered").length;
    const auditLogs = logs.filter((log) => log.action);

    return (
      <>
        <PageHeader
          eyebrow="Governance"
          title="Every answer has a reason."
          copy="Review escalations, low-confidence matches, blocked responses, source usage, and the scores behind each decision."
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
            {logs.length ? (
              <div className="space-y-3">
                {logs.map((log, index) => {
                  const key = log.id ?? `${log.question ?? "log"}-${index}`;
                  return (
                    <article key={key} className="rounded-[8px] border border-line p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm text-ink/56">{log.timestamp ?? "Recent"}</p>
                          <h3 className="mt-2 text-lg font-semibold">{log.question ?? "Decision event"}</h3>
                        </div>
                        <StatusBadge tone={statusTone(log.decision ?? "neutral")}>
                          {log.decision ?? "logged"}
                        </StatusBadge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-ink/68">{log.reason ?? "No reason recorded."}</p>
                      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
                        <div className="rounded-[8px] bg-mist p-3">
                          <p className="text-ink/52">Source</p>
                          <p className="mt-1 font-semibold">{log.source ?? "None"}</p>
                        </div>
                        <div className="rounded-[8px] bg-mist p-3">
                          <p className="text-ink/52">Similarity</p>
                          <p className="mt-1 font-semibold">{formatScore(log.similarity ?? null)}</p>
                        </div>
                        <div className="rounded-[8px] bg-mist p-3">
                          <p className="text-ink/52">Groundedness</p>
                          <p className="mt-1 font-semibold">{formatScore(log.groundedness ?? null)}</p>
                        </div>
                        <div className="rounded-[8px] bg-mist p-3">
                          <p className="text-ink/52">Safety</p>
                          <p className="mt-1 font-semibold">{formatScore(log.safety ?? null)}</p>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No governance events yet"
                copy="Decision events will appear here as customer conversations are answered, escalated, or blocked."
              />
            )}
          </Panel>

          <div className="space-y-6">
            <Panel title="Needs review" eyebrow="Trust queue">
              <div className="space-y-3">
                {logs
                  .filter((log) => log.decision && log.decision !== "answered")
                  .map((log, index) => (
                    <div key={log.id ?? `${log.decision ?? "review"}-${index}`} className="rounded-[8px] border border-line bg-paper p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-semibold">{log.decision}</p>
                        <StatusBadge tone={statusTone(log.decision ?? "neutral")}>
                          {formatScore(log.groundedness ?? null)}
                        </StatusBadge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-ink/66">{log.reason ?? "Needs review."}</p>
                    </div>
                  ))}
              </div>
            </Panel>

            <Panel title="Audit activity" eyebrow="Configuration changes">
              {auditLogs.length ? (
                <div className="space-y-3">
                  {auditLogs.map((event, index) => (
                    <div key={event.id ?? `${event.action ?? "audit"}-${index}`} className="rounded-[8px] border border-line p-4">
                      <p className="text-sm font-semibold">{event.action}</p>
                      <p className="mt-2 text-sm leading-6 text-ink/64">
                        {event.resourceType ?? "resource"} {event.resourceId ?? ""}
                      </p>
                      <p className="mt-3 text-xs text-ink/52">
                        {event.actorEmail ?? event.actorUserId ?? "system"} - {event.timestamp ?? "Recent"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No recent configuration changes"
                  copy="When tenant settings, integrations, billing access, or governance rules change, the audit activity will appear here."
                />
              )}
            </Panel>
          </div>
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
