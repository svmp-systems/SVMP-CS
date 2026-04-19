import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";
import Link from "next/link";

export default async function SessionsPage() {
  const { sessions } = await api.getSessions();

  return (
    <>
      <PageHeader
        eyebrow="Sessions"
        title="Every customer conversation, searchable and reviewable."
        copy="See what the customer asked, what SVMP answered, what source it used, and why anything escalated."
        action={
          <div className="flex gap-2">
            <input
              aria-label="Search conversations"
              placeholder="Search sessions"
              className="h-11 rounded-[8px] border border-line bg-white px-3 text-sm outline-none focus:border-pine"
            />
            <button className="rounded-[8px] bg-ink px-4 py-2 text-sm font-semibold text-paper">
              Export
            </button>
          </div>
        }
      />

      <Panel title="Conversation list" eyebrow={`${sessions.length} recent sessions`}>
        <div className="overflow-hidden rounded-[8px] border border-line">
          <div className="hidden grid-cols-[1.3fr_0.7fr_0.7fr_0.7fr_0.6fr] gap-4 border-b border-line bg-mist px-4 py-3 text-xs font-semibold uppercase text-ink/58 lg:grid">
            <span>Question</span>
            <span>Status</span>
            <span>Confidence</span>
            <span>Source</span>
            <span>Provider</span>
          </div>
          <div className="divide-y divide-line">
            {sessions.map((session) => (
              <Link
                key={session.id ?? session._id}
                href={`/sessions/${session.id ?? session._id}`}
                className="grid gap-3 p-4 hover:bg-paper lg:grid-cols-[1.3fr_0.7fr_0.7fr_0.7fr_0.6fr] lg:items-center"
              >
                <div>
                  <p className="font-semibold">{session.question ?? session.latestMessage ?? "Customer conversation"}</p>
                  <p className="mt-1 text-sm text-ink/58">{session.customer ?? session.userId ?? "Customer"} - {session.timestamp ?? session.updatedAt ?? "Latest"}</p>
                </div>
                <StatusBadge tone={statusTone(session.status ?? session.dashboardStatus ?? "pending")}>{session.status ?? session.dashboardStatus ?? "pending"}</StatusBadge>
                <p className="text-sm font-semibold">
                  {session.confidence === null || session.confidence === undefined ? "Waiting" : session.confidence.toFixed(2)}
                </p>
                <p className="text-sm text-ink/64">{session.source ?? "No source yet"}</p>
                <p className="text-sm text-ink/64">{session.provider}</p>
              </Link>
            ))}
          </div>
        </div>
      </Panel>
    </>
  );
}
