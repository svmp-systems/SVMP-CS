"use client";

import { FormEvent, useState } from "react";

const included = [
  "WhatsApp-first support setup",
  "Approved knowledge base onboarding",
  "Brand voice and escalation controls",
  "Private portal access",
  "Governance visibility",
  "Billing and rollout support",
] as const;

const pricingDrivers = [
  "support volume and how often customers reach out",
  "knowledge base depth and onboarding complexity",
  "governance, escalation, and review needs",
  "WhatsApp setup and rollout requirements",
] as const;

type DemoFormState = {
  name: string;
  email: string;
  company: string;
  teamSize: string;
  message: string;
};

const initialFormState: DemoFormState = {
  name: "",
  email: "",
  company: "",
  teamSize: "",
  message: "",
};

export function PricingPageClient() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [formState, setFormState] = useState<DemoFormState>(initialFormState);

  function openModal() {
    setIsModalOpen(true);
    setIsSubmitted(false);
  }

  function closeModal() {
    setIsModalOpen(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitted(true);
  }

  return (
    <>
      <section className="section-pad border-b border-line">
        <div className="mx-auto max-w-7xl py-16 md:py-20 lg:py-24">
          <div className="max-w-4xl">
            <p className="text-[15px] font-semibold text-pine">Pricing</p>
            <h1 className="mt-6 max-w-5xl font-serif text-5xl leading-[1.04] md:text-6xl lg:text-7xl">
              Start with the rollout that fits the team.
            </h1>
            <p className="mt-7 max-w-3xl text-xl leading-9 text-ink/72">
              SVMP CS pricing is better handled as a guided rollout than a self-serve
              checkout. The structure below makes the buying path clear without
              pretending every team needs the same setup.
            </p>
          </div>
        </div>
      </section>

      <section className="section-pad border-b border-line bg-[#F4F7F2]">
        <div className="mx-auto max-w-7xl py-16 md:py-20 lg:py-24">
          <div className="grid gap-px overflow-hidden rounded-[8px] border border-line bg-line lg:grid-cols-[1.05fr_0.95fr]">
            <article className="bg-paper p-7 md:p-8">
              <p className="text-[13px] font-semibold uppercase tracking-[0.12em] text-pine">
                Custom pricing
              </p>
              <h2 className="mt-5 font-serif text-4xl leading-tight md:text-5xl">
                One rollout path, priced around the actual support workflow.
              </h2>
              <p className="mt-6 max-w-2xl text-[17px] leading-8 text-ink/68">
                SVMP CS is priced after understanding how the support team works,
                what the AI should handle, and what kind of rollout the business
                needs. The goal is to shape a setup that fits the workflow instead of
                forcing the team into a fake plan.
              </p>
              <div className="mt-8 inline-flex rounded-[8px] border border-line bg-[#F8FAF6] px-4 py-3 text-[15px] font-semibold">
                Pricing depends on the workflow, not a pre-set tier
              </div>
              <div className="mt-8">
                <button
                  type="button"
                  onClick={openModal}
                  className="rounded-[8px] bg-ink px-5 py-3 text-[15px] font-semibold text-paper hover:bg-pine"
                >
                  Request a demo
                </button>
              </div>
            </article>

            <article className="bg-paper p-7 md:p-8">
              <p className="text-[15px] font-semibold text-pine">What pricing depends on</p>
              <ul className="mt-6 space-y-4 text-[16px] leading-8 text-ink/72">
                {pricingDrivers.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
              <div className="mt-8 rounded-[8px] border border-line bg-[#F8FAF6] p-5">
                <p className="text-[14px] font-semibold text-pine">Next step</p>
                <p className="mt-3 text-[16px] leading-8 text-ink/68">
                  Request a demo, share the support setup, and the rollout can be
                  shaped from there.
                </p>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section className="section-pad border-b border-line">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[0.7fr_1.3fr] lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-pine">Included</p>
            <h2 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              What the rollout is built around.
            </h2>
          </div>
          <div className="grid gap-px overflow-hidden rounded-[8px] border border-line bg-line md:grid-cols-2">
            {included.map((item) => (
              <article key={item} className="bg-paper p-7">
                <p className="text-xl font-semibold">{item}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[1fr_0.8fr] lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-pine">Next step</p>
            <h2 className="mt-5 max-w-4xl font-serif text-5xl leading-tight md:text-6xl">
              Structured onboarding for paid support teams.
            </h2>
          </div>
          <div>
            <p className="text-xl leading-9 text-ink/72">
              Each workspace is configured around tenant setup, approved knowledge,
              brand voice, billing, WhatsApp connection, governance review, and a
              controlled go-live path.
            </p>
            <p className="mt-8 text-[16px] leading-8 text-ink/64">
              The demo request above captures the details needed to shape pricing and
              rollout around the actual workflow, instead of forcing the team to pick
              a pre-set plan.
            </p>
          </div>
        </div>
      </section>

      {isModalOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-5 py-8"
          role="dialog"
          aria-modal="true"
          aria-labelledby="demo-request-title"
        >
          <div className="w-full max-w-2xl rounded-[12px] border border-line bg-paper shadow-[0_24px_90px_rgba(21,25,21,0.16)]">
            <div className="flex items-start justify-between gap-6 border-b border-line px-6 py-5">
              <div>
                <p className="text-[14px] font-semibold text-pine">Request a demo</p>
                <h2
                  id="demo-request-title"
                  className="mt-2 font-serif text-4xl leading-tight"
                >
                  Tell us about the team.
                </h2>
              </div>
              <button
                type="button"
                onClick={closeModal}
                className="rounded-[8px] border border-line px-3 py-2 text-[14px] font-semibold hover:border-ink"
              >
                Close
              </button>
            </div>

            {isSubmitted ? (
              <div className="px-6 py-7">
                <p className="text-[15px] font-semibold text-pine">Thanks</p>
                <h3 className="mt-3 font-serif text-3xl leading-tight">
                  Demo request captured.
                </h3>
                <p className="mt-4 max-w-xl text-[17px] leading-8 text-ink/72">
                  This is a frontend-only preview for now, so nothing has been sent
                  yet. The flow is ready for a real backend or email integration next.
                </p>
                <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-[8px] bg-ink px-5 py-3 text-[15px] font-semibold text-paper hover:bg-pine"
                  >
                    Done
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsSubmitted(false);
                      setFormState(initialFormState);
                    }}
                    className="rounded-[8px] border border-line px-5 py-3 text-[15px] font-semibold hover:border-ink"
                  >
                    Edit details
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="grid gap-5 px-6 py-7">
                <div className="grid gap-5 md:grid-cols-2">
                  <label className="grid gap-2 text-[15px] font-medium">
                    Name
                    <input
                      required
                      value={formState.name}
                      onChange={(event) =>
                        setFormState((current) => ({ ...current, name: event.target.value }))
                      }
                      className="rounded-[8px] border border-line bg-white px-4 py-3 text-[15px] outline-none transition focus:border-ink"
                      placeholder="Name"
                    />
                  </label>
                  <label className="grid gap-2 text-[15px] font-medium">
                    Work email
                    <input
                      required
                      type="email"
                      value={formState.email}
                      onChange={(event) =>
                        setFormState((current) => ({ ...current, email: event.target.value }))
                      }
                      className="rounded-[8px] border border-line bg-white px-4 py-3 text-[15px] outline-none transition focus:border-ink"
                      placeholder="team@company.com"
                    />
                  </label>
                </div>

                <div className="grid gap-5 md:grid-cols-2">
                  <label className="grid gap-2 text-[15px] font-medium">
                    Company
                    <input
                      required
                      value={formState.company}
                      onChange={(event) =>
                        setFormState((current) => ({ ...current, company: event.target.value }))
                      }
                      className="rounded-[8px] border border-line bg-white px-4 py-3 text-[15px] outline-none transition focus:border-ink"
                      placeholder="Team or company name"
                    />
                  </label>
                  <label className="grid gap-2 text-[15px] font-medium">
                    Team size
                    <select
                      required
                      value={formState.teamSize}
                      onChange={(event) =>
                        setFormState((current) => ({ ...current, teamSize: event.target.value }))
                      }
                      className="rounded-[8px] border border-line bg-white px-4 py-3 text-[15px] outline-none transition focus:border-ink"
                    >
                      <option value="">Select</option>
                      <option value="1-5">1-5</option>
                      <option value="6-20">6-20</option>
                      <option value="21-50">21-50</option>
                      <option value="51+">51+</option>
                    </select>
                  </label>
                </div>

                <label className="grid gap-2 text-[15px] font-medium">
                  What should the rollout cover?
                  <textarea
                    rows={5}
                    value={formState.message}
                    onChange={(event) =>
                      setFormState((current) => ({ ...current, message: event.target.value }))
                    }
                    className="rounded-[8px] border border-line bg-white px-4 py-3 text-[15px] outline-none transition focus:border-ink"
                    placeholder="Support volume, workflow needs, rollout questions, or anything else."
                  />
                </label>

                <div className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row">
                  <button
                    type="submit"
                    className="rounded-[8px] bg-ink px-5 py-3 text-[15px] font-semibold text-paper hover:bg-pine"
                  >
                    Request demo
                  </button>
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-[8px] border border-line px-5 py-3 text-[15px] font-semibold hover:border-ink"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
