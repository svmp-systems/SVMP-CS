import Link from "next/link";
import { navItems } from "@/components/marketing/content";

export function MarketingHeader() {
  return (
    <header className="section-pad border-b border-line bg-paper">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6">
        <Link href="/" className="text-[15px] font-semibold" aria-label="SVMP CS home">
          SVMP CS
        </Link>
        <div className="hidden items-center gap-8 text-[15px] text-ink/70 md:flex">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} className="hover:text-ink">
              {item.label}
            </Link>
          ))}
        </div>
        <Link
          href="/signin"
          prefetch={false}
          className="rounded-[8px] bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-pine"
        >
          Login
        </Link>
      </nav>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="section-pad border-t border-line">
      <div className="mx-auto grid max-w-7xl gap-8 py-10 md:grid-cols-[1fr_auto]">
        <div>
          <p className="text-[15px] font-semibold">SVMP</p>
          <p className="mt-3 max-w-2xl text-[15px] leading-7 text-ink/62">
            Governed AI customer support for businesses that need approved knowledge,
            clear escalation, and inspectable decisions.
          </p>
        </div>
        <div className="grid gap-3 text-[15px] text-ink/62 sm:grid-cols-2 sm:gap-x-8">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} className="hover:text-ink">
              {item.label}
            </Link>
          ))}
          <Link href="/signin" prefetch={false} className="hover:text-ink">
            Login
          </Link>
        </div>
      </div>
    </footer>
  );
}

export function Arrow() {
  return <span className="hidden h-px flex-1 bg-line lg:block" aria-hidden="true" />;
}
