import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";

const examples = [
  "Yes, that fragrance is available in the current collection.",
  "I can help with that. For order-specific details, I will connect you with the team.",
  "That offer depends on the active checkout promotion, so the final price should be confirmed at checkout.",
];

export default function BrandVoicePage() {
  return (
    <>
      <PageHeader
        eyebrow="Brand voice"
        title="Control how SVMP sounds before it answers customers."
        copy="Set tone, required language, blocked language, and the escalation style used when confidence is low."
        action={
          <button className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
            Save voice
          </button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <Panel title="Voice rules" eyebrow="Editable settings">
          <div className="grid gap-5">
            <label className="grid gap-2">
              <span className="text-sm font-semibold">Tone description</span>
              <textarea
                rows={4}
                defaultValue="Warm, polished, premium, concise, and helpful."
                className="rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
              />
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Use these words</span>
                <textarea
                  rows={5}
                  defaultValue={"concise\nhelpful\nconfident\nclear"}
                  className="rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
                />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Avoid these words</span>
                <textarea
                  rows={5}
                  defaultValue={"overpromising\nslang\nguaranteed forever\ncheap"}
                  className="rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
                />
              </label>
            </div>
            <label className="grid gap-2">
              <span className="text-sm font-semibold">Escalation style</span>
              <textarea
                rows={3}
                defaultValue="Apologetic and clear. Say that the team will follow up because the answer depends on order-specific or policy-sensitive details."
                className="rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
              />
            </label>
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Example replies" eyebrow="Approved tone">
            <div className="space-y-3">
              {examples.map((example) => (
                <div key={example} className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/72">
                  {example}
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Preview" eyebrow="Ask a test question">
            <label className="text-sm font-semibold" htmlFor="voice-test">
              Customer question
            </label>
            <textarea
              id="voice-test"
              rows={4}
              defaultValue="Can I return a fragrance if I opened it?"
              className="mt-3 w-full rounded-[8px] border border-line bg-paper p-3 text-sm outline-none focus:border-pine"
            />
            <div className="mt-5 rounded-[8px] border border-line bg-paper p-4">
              <p className="text-sm font-semibold">SVMP preview</p>
              <p className="mt-2 text-sm leading-6 text-ink/68">
                I can help with returns. Because opened-product eligibility can depend on the exact order and policy details, I will connect you with the support team to confirm the next step.
              </p>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
