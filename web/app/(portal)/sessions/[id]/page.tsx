import { EmptyState } from "@/components/portal/empty-state";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import type { SessionMessage } from "@/services/api/types";
import { notFound, redirect } from "next/navigation";

function speakerLabel(message: SessionMessage) {
  return message.speaker ?? message.sender ?? message.role ?? "system";
}

function messageTimestamp(message: SessionMessage) {
  return message.at ?? message.timestamp ?? message.createdAt ?? "Recent";
}

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  try {
    const api = await getServerApi();
    const { session, governanceLogs } = await api.getSession(id);
    const transcript = session.transcript ?? session.messages ?? [];
    const status = session.dashboardStatus ?? session.status ?? "pending";
    const answeredLog = governanceLogs.find((log) => log.decision === "answered");
    const escalatedLog = governanceLogs.find((log) => log.decision === "escalated");
    const answeredPayload =
      answeredLog?.after && typeof answeredLog.after === "object"
        ? (answeredLog.after as Record<string, unknown>)
        : null;
    const answerBody =
      session.answer ??
      (answeredPayload && "response" in answeredPayload
        ? String(answeredPayload.response)
        : null);

    return (
      <>
        <PageHeader
          eyebrow="Session detail"
          title={session.question ?? session.latestMessage ?? "Customer conversation"}
          copy={`${session.userId ?? session.clientId ?? "Customer"} on ${session.provider ?? "provider"}. ${session.updatedAt ?? session.createdAt ?? "Recent"}.`}
          action={<StatusBadge tone={statusTone(status)}>{status}</StatusBadge>}
        />

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <Panel title="Transcript" eyebrow="Customer thread">
            {transcript.length ? (
              <div className="space-y-3">
                {transcript.map((message, index) => (
                  <div
                    key={`${messageTimestamp(message)}-${index}`}
                    className="rounded-[8px] border border-line bg-paper p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold capitalize">{speakerLabel(message)}</p>
                      <p className="text-xs text-ink/52">{messageTimestamp(message)}</p>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-ink/72">{message.text}</p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Transcript not available yet"
                copy="This session has been recorded, but the detailed message thread has not been returned on this response."
              />
            )}
          </Panel>

          <div className="space-y-6">
            <Panel title="Decision" eyebrow="SVMP CS outcome">
              <div className="space-y-4">
                <div className="rounded-[8px] border border-line p-4">
                  <p className="text-sm font-semibold text-ink/60">Answer</p>
                  <p className="mt-2 text-sm leading-6 text-ink/76">
                    {answerBody ?? "No final answer was recorded before this session moved to escalation or review."}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-[8px] border border-line p-4">
                    <p className="text-sm font-semibold text-ink/60">Matched source</p>
                    <p className="mt-2 text-sm text-ink/76">{session.source ?? answeredLog?.source ?? "None"}</p>
                  </div>
                  <div className="rounded-[8px] border border-line p-4">
                    <p className="text-sm font-semibold text-ink/60">Confidence</p>
                    <p className="mt-2 text-sm text-ink/76">
                      {answeredLog?.similarity == null ? "Not scored" : answeredLog.similarity.toFixed(2)}
                    </p>
                  </div>
                </div>
                {escalatedLog?.reason ? (
                  <div className="rounded-[8px] border border-berry/20 bg-berry/10 p-4">
                    <p className="text-sm font-semibold text-berry">Escalation reason</p>
                    <p className="mt-2 text-sm leading-6 text-ink/76">{escalatedLog.reason}</p>
                  </div>
                ) : null}
              </div>
            </Panel>

            <Panel title="Audit details" eyebrow="Governance">
              <dl className="grid gap-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-ink/58">Safety score</dt>
                  <dd className="font-semibold">
                    {answeredLog?.safety == null ? "Not scored" : answeredLog.safety.toFixed(2)}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-ink/58">Provider</dt>
                  <dd className="font-semibold">{session.provider ?? "Unknown"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-ink/58">Session ID</dt>
                  <dd className="font-semibold">{session.id}</dd>
                </div>
              </dl>
            </Panel>
          </div>
        </div>
      </>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
