import { EmptyState } from "@/components/portal/empty-state";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";

export default async function KnowledgeBasePage() {
  const { entries } = await api.getKnowledgeBase();
  const activeEntries = entries.filter((entry) => entry.active);

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
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase text-pine">{entry.topic}</p>
                      <h3 className="mt-2 text-lg font-semibold">{entry.question}</h3>
                    </div>
                    <StatusBadge tone={entry.active ? "green" : "neutral"}>
                      {entry.active ? "active" : "inactive"}
                    </StatusBadge>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-ink/68">{entry.answer}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    {entry.tags.map((tag) => (
                      <span key={tag} className="rounded-[8px] bg-mist px-2.5 py-1 text-xs font-semibold text-ink/62">
                        {tag}
                      </span>
                    ))}
                    <span className="ml-auto text-xs text-ink/52">Updated {entry.updatedAt}</span>
                  </div>
                </article>
              ))
            ) : (
              <EmptyState title="No knowledge yet" copy="Add the first approved FAQ before turning on auto-answering." />
            )}
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Test this KB" eyebrow="Dry run">
            <label className="text-sm font-semibold" htmlFor="kb-test">
              Customer question
            </label>
            <textarea
              id="kb-test"
              rows={5}
              placeholder="Ask something a customer would ask on WhatsApp"
              className="mt-3 w-full rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
              defaultValue="Do you offer free shipping?"
            />
            <button className="mt-4 rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
              Test question
            </button>
            <div className="mt-5 rounded-[8px] border border-line bg-paper p-4">
              <p className="text-sm font-semibold">Preview result</p>
              <p className="mt-2 text-sm leading-6 text-ink/66">
                Matched "Do you offer free shipping?" with confidence 0.92. SVMP would answer from the shipping FAQ.
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
