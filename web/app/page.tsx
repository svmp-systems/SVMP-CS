const navItems = [
  { label: "How it works", href: "#how-it-works" },
  { label: "Dashboard", href: "#dashboard" },
  { label: "Safety", href: "#safety" },
  { label: "Access", href: "#access" },
];

const flow = [
  {
    label: "Customer asks on WhatsApp",
    detail: "Messages can arrive as fragments, follow-ups, or repeated questions.",
  },
  {
    label: "SVMP checks approved knowledge",
    detail: "It uses the tenant's FAQ, policies, domains, and brand voice.",
  },
  {
    label: "Answer or escalate",
    detail: "High-confidence answers go out. Unclear cases go to a human.",
  },
  {
    label: "Everything is logged",
    detail: "The portal shows the answer, source, score, reason, and status.",
  },
];

const outcomes = [
  ["For customers", "Fast answers on WhatsApp, without waiting for a human on simple questions."],
  ["For support teams", "Fewer repetitive replies, clearer escalations, and a record of what happened."],
  ["For owners", "A dashboard for savings, safety, knowledge gaps, and AI behavior."],
];

const portalRows = [
  ["Overview", "Deflection rate, human hours saved, resolution time, safety score"],
  ["Sessions", "Customer question, SVMP answer, confidence, source, escalation reason"],
  ["Knowledge base", "Approved FAQs, active state, topic filters, test questions"],
  ["Brand voice", "Tone, words to use, words to avoid, escalation style"],
  ["Governance", "Low-confidence answers, blocked responses, audit trail"],
];

const safety = [
  {
    title: "Approved knowledge only",
    copy: "SVMP answers from the knowledge base and settings the business controls.",
  },
  {
    title: "Confidence threshold",
    copy: "If the score is too low, SVMP does not force an answer.",
  },
  {
    title: "Human escalation",
    copy: "Unclear questions are routed for follow-up instead of being guessed at.",
  },
  {
    title: "Audit trail",
    copy: "Every outcome keeps the question, answer, source, score, and reason together.",
  },
];

const buildStatus = [
  ["Backend", "FastAPI runtime with WhatsApp webhook intake"],
  ["Database", "MongoDB tenants, sessions, knowledge base, governance logs"],
  ["Portal", "Customer dashboard for paid tenant configuration and monitoring"],
];

function Arrow() {
  return (
    <span className="hidden h-px flex-1 bg-line lg:block" aria-hidden="true" />
  );
}

export default function Home() {
  return (
    <main className="min-h-screen bg-paper text-ink">
      <header className="section-pad border-b border-line bg-paper">
        <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6">
          <a href="#" className="text-[15px] font-semibold" aria-label="SVMP home">
            SVMP
          </a>
          <div className="hidden items-center gap-8 text-[15px] text-ink/70 md:flex">
            {navItems.map((item) => (
              <a key={item.href} href={item.href} className="hover:text-ink">
                {item.label}
              </a>
            ))}
          </div>
          <a
            href="/login"
            className="rounded-[8px] border border-ink px-4 py-2 text-[15px] font-medium hover:bg-ink hover:text-paper"
          >
            Login
          </a>
        </nav>
      </header>

      <section className="section-pad border-b border-line">
        <div className="mx-auto max-w-7xl py-16 md:py-20 lg:py-24">
          <div className="max-w-4xl">
            <p className="text-[15px] font-semibold text-pine">
              AI support for WhatsApp-first businesses
            </p>
            <h1 className="mt-6 max-w-5xl font-serif text-5xl leading-[1.04] md:text-6xl lg:text-7xl">
              SVMP answers customer questions from your approved knowledge base.
            </h1>
            <p className="mt-7 max-w-3xl text-xl leading-9 text-ink/72">
              It connects to WhatsApp, understands fragmented customer messages, answers only when confidence is high, escalates the rest, and shows every decision in a private dashboard.
            </p>
          </div>

          <div className="mt-10 flex flex-col gap-3 sm:flex-row">
            <a
              href="mailto:hello@svmpsystems.com?subject=SVMP%20demo"
              className="rounded-[8px] bg-ink px-5 py-3 text-center text-[15px] font-semibold text-paper hover:bg-pine"
            >
              Book a demo
            </a>
            <a
              href="#how-it-works"
              className="rounded-[8px] border border-line px-5 py-3 text-center text-[15px] font-semibold hover:border-ink"
            >
              See how it works
            </a>
          </div>

          <div className="mt-14 grid gap-px overflow-hidden rounded-[8px] border border-line bg-line lg:grid-cols-3">
            {outcomes.map(([title, copy]) => (
              <div key={title} className="bg-paper p-6">
                <p className="text-[15px] font-semibold">{title}</p>
                <p className="mt-4 text-[16px] leading-8 text-ink/68">{copy}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className="section-pad border-b border-line bg-[#F4F7F2]">
        <div className="mx-auto max-w-7xl py-16 md:py-20">
          <div className="grid gap-8 lg:grid-cols-[0.55fr_1.45fr]">
            <div>
              <p className="text-[15px] font-semibold text-pine">What it does</p>
              <h2 className="mt-4 font-serif text-4xl leading-tight md:text-5xl">
                The whole loop, without the jargon.
              </h2>
            </div>
            <div className="grid gap-4 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] lg:items-stretch">
              {flow.map((item, index) => (
                <div key={item.label} className="contents">
                  <article className="rounded-[8px] border border-line bg-paper p-5">
                    <p className="font-serif text-3xl text-berry">0{index + 1}</p>
                    <h3 className="mt-8 text-xl font-semibold">{item.label}</h3>
                    <p className="mt-4 text-[15px] leading-7 text-ink/66">{item.detail}</p>
                  </article>
                  {index < flow.length - 1 ? <Arrow /> : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad border-b border-line">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[0.75fr_1.25fr] lg:items-center lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-pine">Product surface</p>
            <h2 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              A support system, not a loose chatbot.
            </h2>
            <p className="mt-7 text-xl leading-9 text-ink/72">
              The dashboard is where a business controls what SVMP knows, how it speaks, when it escalates, and what it did in each customer conversation.
            </p>
          </div>

          <div className="overflow-hidden rounded-[8px] border border-line bg-white">
            <img
              src="/portal-overview.png"
              alt="SVMP customer portal overview dashboard"
              className="block w-full"
            />
          </div>
        </div>
      </section>

      <section id="dashboard" className="section-pad border-b border-line bg-ink text-paper">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[0.85fr_1.15fr] lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-citron">Private portal</p>
            <h2 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              What paid clients actually get.
            </h2>
            <p className="mt-8 text-xl leading-9 text-paper/72">
              A dashboard to monitor value, control answers, update knowledge, inspect escalations, and govern the AI support system.
            </p>
          </div>
          <div className="overflow-hidden rounded-[8px] border border-paper/18">
            {portalRows.map(([name, description]) => (
              <div
                key={name}
                className="grid gap-3 border-b border-paper/14 p-5 last:border-b-0 md:grid-cols-[11rem_1fr]"
              >
                <p className="font-semibold">{name}</p>
                <p className="leading-7 text-paper/68">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="safety" className="section-pad border-b border-line">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[0.7fr_1.3fr] lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-pine">Safety</p>
            <h2 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              The point is control.
            </h2>
          </div>
          <div className="grid gap-px overflow-hidden rounded-[8px] border border-line bg-line md:grid-cols-2">
            {safety.map((item) => (
              <article key={item.title} className="bg-paper p-7">
                <h3 className="text-2xl font-semibold">{item.title}</h3>
                <p className="mt-5 text-[16px] leading-8 text-ink/68">{item.copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section-pad border-b border-line bg-[#F4F7F2]">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-pine">WhatsApp first</p>
            <h2 className="mt-5 font-serif text-5xl leading-tight md:text-6xl">
              Start where customer conversations already happen.
            </h2>
            <p className="mt-7 text-xl leading-9 text-ink/72">
              SVMP's first live channel is WhatsApp. Future integrations can come later; the first product is focused on one support flow working well.
            </p>
          </div>
          <div className="overflow-hidden rounded-[8px] border border-line bg-paper">
            <div className="border-b border-line p-5">
              <p className="text-[13px] text-ink/54">What changes</p>
              <h3 className="mt-1 text-2xl font-semibold">From repeat work to governed automation</h3>
            </div>
            <div className="grid gap-px bg-line md:grid-cols-2">
              <div className="bg-paper p-6">
                <p className="text-[13px] font-semibold uppercase text-berry">Before</p>
                <ul className="mt-8 space-y-5 text-[16px] leading-7 text-ink/70">
                  <li>Agents repeat the same shipping, pricing, and product answers.</li>
                  <li>WhatsApp threads are fragmented and hard to summarize.</li>
                  <li>Owners cannot easily inspect what was said or why.</li>
                  <li>Knowledge gaps stay hidden until customers complain.</li>
                </ul>
              </div>
              <div className="bg-paper p-6">
                <p className="text-[13px] font-semibold uppercase text-pine">With SVMP</p>
                <ul className="mt-8 space-y-5 text-[16px] leading-7 text-ink/70">
                  <li>Safe repeat questions are answered from approved KB entries.</li>
                  <li>Low-confidence questions are escalated with reasons attached.</li>
                  <li>Every decision keeps source, score, provider, and timestamp.</li>
                  <li>Metrics show deflection, hours saved, and missing knowledge.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad border-b border-line">
        <div className="mx-auto grid max-w-7xl gap-10 py-14 lg:grid-cols-[0.34fr_1fr]">
          <div>
            <p className="text-[15px] font-semibold">Build status</p>
          </div>
          <div className="grid gap-px overflow-hidden rounded-[8px] border border-line bg-line md:grid-cols-3">
            {buildStatus.map(([title, copy]) => (
              <article key={title} className="bg-paper p-6">
                <h3 className="text-xl font-semibold">{title}</h3>
                <p className="mt-5 text-[15px] leading-7 text-ink/68">{copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="access" className="section-pad">
        <div className="mx-auto grid max-w-7xl gap-12 py-20 lg:grid-cols-[1fr_0.8fr] lg:py-28">
          <div>
            <p className="text-[15px] font-semibold text-pine">Private rollout</p>
            <h2 className="mt-5 max-w-4xl font-serif text-5xl leading-tight md:text-6xl">
              Built with paid clients before public self-serve.
            </h2>
          </div>
          <div>
            <p className="text-xl leading-9 text-ink/72">
              SVMP is being shaped as a guided deployment first: tenant setup, knowledge base, brand voice, WhatsApp connection, governance review, and then go-live.
            </p>
            <a
              href="mailto:hello@svmpsystems.com?subject=SVMP%20demo"
              className="mt-8 inline-flex rounded-[8px] bg-ink px-5 py-3 text-[15px] font-semibold text-paper hover:bg-pine"
            >
              Request access
            </a>
          </div>
        </div>
      </section>

      <footer className="section-pad border-t border-line">
        <div className="mx-auto grid max-w-7xl gap-8 py-10 md:grid-cols-[1fr_auto]">
          <div>
            <p className="text-[15px] font-semibold">SVMP</p>
            <p className="mt-3 max-w-2xl text-[15px] leading-7 text-ink/62">
              Governed AI customer support for businesses that need approved knowledge, clear escalation, and inspectable decisions.
            </p>
          </div>
          <div className="grid gap-3 text-[15px] text-ink/62 sm:grid-cols-2 sm:gap-x-8">
            <a href="#how-it-works" className="hover:text-ink">How it works</a>
            <a href="#dashboard" className="hover:text-ink">Dashboard</a>
            <a href="#safety" className="hover:text-ink">Safety</a>
            <a href="/login" className="hover:text-ink">Login</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
