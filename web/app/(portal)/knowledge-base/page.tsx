import { EmptyState } from "@/components/portal/empty-state";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";
import {
  createKnowledgeEntryAction,
  deleteKnowledgeEntryAction,
  testQuestionAction,
  updateKnowledgeEntryAction,
} from "@/lib/actions";

type SearchParams = Promise<{ error?: string; test?: string }>;

export default async function KnowledgeBasePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const { entries } = await api.getKnowledgeBase();
  const activeEntries = entries.filter((entry) => entry.active);
  const testResult = params.test ? JSON.parse(params.test) : null;

  return (
    <>
      <PageHeader
        eyebrow="Knowledge base"
        title="The approved source SVMP is allowed to answer from."
        copy="Add, update, deactivate, import, and test FAQ entries before they influence customer replies."
        action={
          <div className="flex flex-wrap gap-2">
            <button className="rounded-[8px] border border-line bg-white px-4 py-3 text-sm font-semibold hover:border-ink">
              Bulk import
            </button>
            <button className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
              Add FAQ
            </button>
          </div>
        }
      />

      {params.error ? (
        <div className="mb-6 rounded-[8px] border border-berry/20 bg-berry/10 p-4 text-sm font-semibold text-berry">
          {params.error}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel title="FAQ entries" eyebrow={`${activeEntries.length} active`}>
          <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto]">
            <input
              aria-label="Search knowledge base"
              placeholder="Search question, answer, topic, or tag"
              className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
            />
            <select className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine">
              <option>All topics</option>
              <option>Shipping</option>
              <option>Pricing</option>
              <option>Returns</option>
            </select>
          </div>

          <div className="space-y-3">
            {entries.length ? (
              entries.map((entry) => (
                <article key={entry.id} className="rounded-[8px] border border-line p-4">
                  <form action={updateKnowledgeEntryAction} className="grid gap-3">
                    <input type="hidden" name="id" value={entry.id ?? entry._id} />
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <input
                          name="domainId"
                          aria-label="Domain"
                          defaultValue={entry.topic ?? entry.domainId ?? "general"}
                          className="w-full rounded-[8px] border border-line bg-paper px-3 py-2 text-xs font-semibold uppercase text-pine outline-none focus:border-pine"
                        />
                        <input
                          name="question"
                          aria-label="Question"
                          defaultValue={entry.question}
                          className="mt-2 w-full rounded-[8px] border border-line bg-paper px-3 py-2 text-lg font-semibold outline-none focus:border-pine"
                        />
                      </div>
                      <label className="flex items-center gap-2 text-sm font-semibold">
                        <input name="active" type="checkbox" defaultChecked={entry.active} />
                        <StatusBadge tone={entry.active ? "green" : "neutral"}>
                          {entry.active ? "active" : "inactive"}
                        </StatusBadge>
                      </label>
                    </div>
                    <textarea
                      name="answer"
                      aria-label="Answer"
                      rows={4}
                      defaultValue={entry.answer}
                      className="rounded-[8px] border border-line bg-paper p-3 text-sm leading-6 text-ink/68 outline-none focus:border-pine"
                    />
                    <input
                      name="tags"
                      aria-label="Tags"
                      defaultValue={(entry.tags ?? []).join(", ")}
                      className="rounded-[8px] border border-line bg-paper px-3 py-2 text-sm outline-none focus:border-pine"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button className="rounded-[8px] bg-ink px-3 py-2 text-sm font-semibold text-paper hover:bg-pine">
                        Save
                      </button>
                      <button
                        formAction={deleteKnowledgeEntryAction}
                        className="rounded-[8px] border border-line px-3 py-2 text-sm font-semibold hover:border-berry hover:text-berry"
                      >
                        Deactivate
                      </button>
                      <span className="ml-auto text-xs text-ink/52">Updated {entry.updatedAt ?? "from API"}</span>
                    </div>
                  </form>
                </article>
              ))
            ) : (
              <EmptyState title="No knowledge yet" copy="Add the first approved FAQ before turning on auto-answering." />
            )}
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Add FAQ" eyebrow="Create entry">
            <form action={createKnowledgeEntryAction} className="grid gap-3">
              <input
                name="domainId"
                placeholder="general"
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
              />
              <input
                name="question"
                placeholder="Customer question"
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                required
              />
              <textarea
                name="answer"
                rows={4}
                placeholder="Approved answer"
                className="rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
                required
              />
              <input
                name="tags"
                placeholder="shipping, checkout"
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
              />
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input name="active" type="checkbox" defaultChecked />
                Active
              </label>
              <button className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
                Add FAQ
              </button>
            </form>
          </Panel>

          <Panel title="Test this KB" eyebrow="Dry run">
            <form action={testQuestionAction}>
              <label className="text-sm font-semibold" htmlFor="kb-test">
                Customer question
              </label>
              <textarea
                id="kb-test"
                name="question"
                rows={5}
                placeholder="Ask something a customer would ask on WhatsApp"
                className="mt-3 w-full rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
                defaultValue="Do you offer free shipping?"
              />
              <input type="hidden" name="domainId" value="" />
              <button className="mt-4 rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
                Test question
              </button>
            </form>
            <div className="mt-5 rounded-[8px] border border-line bg-paper p-4">
              <p className="text-sm font-semibold">Preview result</p>
              <p className="mt-2 text-sm leading-6 text-ink/66">
                {testResult
                  ? `${testResult.decision}: ${testResult.reason}. Confidence ${testResult.confidenceScore ?? "n/a"}.`
                  : "Run a test question to see the backend dry-run decision."}
              </p>
            </div>
          </Panel>

          <Panel title="KB gap insights" eyebrow="Needs coverage">
            <div className="space-y-3 text-sm leading-6 text-ink/68">
              <p>Customers are asking about engraving and offer stacking.</p>
              <p>Add a clear rule for custom bottle requests before enabling auto-answering for that topic.</p>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
