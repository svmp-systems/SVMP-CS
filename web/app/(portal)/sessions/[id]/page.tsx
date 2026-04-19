import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";
import { sessions } from "@/lib/mock-data";
import { notFound } from "next/navigation";

export function generateStaticParams() {
  return sessions.map((session) => ({ id: session.id }));
}

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const payload = await api.getSession(id);
  const session = payload.session ?? sessions.find((item) => item.id === id);

  if (!session) {
    notFound();
  }
  const transcript = session.transcript ?? session.messages ?? [];
  const status = session.status ?? session.dashboardStatus ?? "pending";

  return (
    <>
      <PageHeader
        eyebrow="Session detail"
        title={session.question ?? session.latestMessage ?? "Customer conversation"}
        copy={`${session.customer ?? session.userId ?? "Customer"} on ${session.provider ?? "WhatsApp"}. ${session.timestamp ?? session.updatedAt ?? "Latest"}.`}
        action={<StatusBadge tone={statusTone(status)}>{status}</StatusBadge>}
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Panel title="Transcript" eyebrow="Customer thread">
          <div className="space-y-3">
            {transcript.map((message: any, index: number) => (
              <div
                key={`${message.at}-${index}`}
                className="rounded-[8px] border border-line bg-paper p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold capitalize">{message.speaker ?? "customer"}</p>
                  <p className="text-xs text-ink/52">{message.at}</p>
                </div>
                <p className="mt-3 text-sm leading-6 text-ink/72">{message.text}</p>
              </div>
            ))}
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Decision" eyebrow="SVMP outcome">
            <div className="space-y-4">
              <div className="rounded-[8px] border border-line p-4">
                <p className="text-sm font-semibold text-ink/60">Answer</p>
                <p className="mt-2 text-sm leading-6 text-ink/76">
                  {session.answer ?? "No answer was sent. This session is pending or escalated."}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-[8px] border border-line p-4">
                  <p className="text-sm font-semibold text-ink/60">Matched source</p>
                  <p className="mt-2 text-sm text-ink/76">{session.source ?? "None"}</p>
                </div>
                <div className="rounded-[8px] border border-line p-4">
                  <p className="text-sm font-semibold text-ink/60">Confidence</p>
                  <p className="mt-2 text-sm text-ink/76">
                    {session.confidence === null || session.confidence === undefined ? "Not scored" : session.confidence.toFixed(2)}
                  </p>
                </div>
              </div>
              {session.escalationReason ? (
                <div className="rounded-[8px] border border-berry/20 bg-berry/10 p-4">
                  <p className="text-sm font-semibold text-berry">Escalation reason</p>
                  <p className="mt-2 text-sm leading-6 text-ink/76">{session.escalationReason}</p>
                </div>
              ) : null}
            </div>
          </Panel>

          <Panel title="Audit details" eyebrow="Governance">
            <dl className="grid gap-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-ink/58">Safety score</dt>
                <dd className="font-semibold">{session.safety === null || session.safety === undefined ? "Not scored" : session.safety.toFixed(2)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink/58">Provider</dt>
                <dd className="font-semibold">{session.provider}</dd>
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
}
