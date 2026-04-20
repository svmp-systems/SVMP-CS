import { EmptyState } from "@/components/portal/empty-state";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import type { SessionSummary } from "@/services/api/types";
import Link from "next/link";
import { redirect } from "next/navigation";

function questionText(session: SessionSummary) {
  return session.question ?? session.latestMessage ?? "Customer conversation";
}

function customerLabel(session: SessionSummary) {
  return session.customer ?? session.userId ?? session.clientId ?? "Customer";
}

function sessionStatus(session: SessionSummary) {
  return session.dashboardStatus ?? session.status ?? "pending";
}

function timestampLabel(session: SessionSummary) {
  const raw = session.updatedAt ?? session.createdAt;
  if (!raw) {
    return "Recent";
  }

  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return raw;
  }

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default async function SessionsPage() {
  try {
    const api = await getServerApi();
    const { sessions } = await api.getSessions();

    return (
      <>
        <PageHeader
          eyebrow="Sessions"
          title="Every customer conversation, searchable and reviewable."
          copy="See what the customer asked, what SVMP CS answered, what source it used, and why anything escalated."
        />

        <Panel title="Conversation list" eyebrow={`${sessions.length} recent sessions`}>
          {sessions.length ? (
            <div className="overflow-hidden rounded-[8px] border border-line">
              <div className="hidden grid-cols-[1.3fr_0.7fr_0.7fr_0.7fr_0.6fr] gap-4 border-b border-line bg-mist px-4 py-3 text-xs font-semibold uppercase text-ink/58 lg:grid">
                <span>Question</span>
                <span>Status</span>
                <span>Messages</span>
                <span>Source</span>
                <span>Provider</span>
              </div>
              <div className="divide-y divide-line">
                {sessions.map((session) => {
                  const status = sessionStatus(session);
                  return (
                    <Link
                      key={session.id}
                      href={`/sessions/${session.id}`}
                      className="grid gap-3 p-4 hover:bg-paper lg:grid-cols-[1.3fr_0.7fr_0.7fr_0.7fr_0.6fr] lg:items-center"
                    >
                      <div>
                        <p className="font-semibold">{questionText(session)}</p>
                        <p className="mt-1 text-sm text-ink/58">
                          {customerLabel(session)} - {timestampLabel(session)}
                        </p>
                      </div>
                      <StatusBadge tone={statusTone(status)}>{status}</StatusBadge>
                      <p className="text-sm font-semibold">{session.messageCount ?? 0}</p>
                      <p className="text-sm text-ink/64">{session.source ?? "Awaiting matched source"}</p>
                      <p className="text-sm text-ink/64">{session.provider ?? "Unknown"}</p>
                    </Link>
                  );
                })}
              </div>
            </div>
          ) : (
            <EmptyState
              title="No customer sessions yet"
              copy="New conversations will appear here once the connected channel starts sending tenant traffic through the backend."
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
