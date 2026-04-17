"use client";

import clsx from "clsx";
import {
  BarChart3,
  BookOpen,
  Bot,
  Gauge,
  LayoutDashboard,
  Link2,
  MessageSquareText,
  ScrollText,
  Settings,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "Sessions", href: "/sessions", icon: MessageSquareText },
  { label: "Knowledge Base", href: "/knowledge-base", icon: BookOpen },
  { label: "Brand Voice", href: "/brand-voice", icon: Bot },
  { label: "Governance", href: "/governance", icon: ShieldCheck },
  { label: "Metrics", href: "/metrics", icon: BarChart3 },
  { label: "Integrations", href: "/integrations", icon: Link2 },
  { label: "Settings", href: "/settings", icon: Settings },
];

function isActive(pathname: string, href: string) {
  if (href === "/dashboard") {
    return pathname === "/dashboard";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function PortalShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-paper text-ink">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-72 border-r border-line bg-white lg:block">
        <div className="flex h-full flex-col">
          <div className="border-b border-line p-6">
            <Link href="/" className="text-lg font-semibold">
              SVMP
            </Link>
            <p className="mt-2 text-sm leading-6 text-ink/58">Customer portal</p>
          </div>

          <nav className="flex-1 space-y-1 p-4">
            {navItems.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-sm font-semibold",
                    active
                      ? "bg-ink text-paper"
                      : "text-ink/68 hover:bg-mist hover:text-ink",
                  )}
                >
                  <Icon size={18} strokeWidth={1.8} />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="border-t border-line p-4">
            <div className="rounded-[8px] border border-line bg-paper p-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Gauge size={17} />
                Stay Parfums
              </div>
              <p className="mt-3 text-sm leading-6 text-ink/62">
                Active subscription. WhatsApp is healthy.
              </p>
            </div>
          </div>
        </div>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-10 border-b border-line bg-paper/95 backdrop-blur">
          <div className="flex min-h-16 flex-col gap-3 px-4 py-4 md:px-8 lg:flex-row lg:items-center lg:justify-between">
            <nav className="flex gap-2 overflow-x-auto lg:hidden">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    "whitespace-nowrap rounded-[8px] border px-3 py-2 text-sm font-semibold",
                    isActive(pathname, item.href)
                      ? "border-ink bg-ink text-paper"
                      : "border-line bg-white text-ink/70",
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <div>
              <p className="text-sm font-semibold text-pine">Stay Parfums</p>
              <p className="mt-1 text-sm text-ink/58">
                Tenant: stay. Role: owner. Subscription: active.
              </p>
            </div>
            <Link
              href="/settings"
              className="hidden rounded-[8px] border border-line bg-white px-4 py-2 text-sm font-semibold hover:border-ink lg:inline-flex"
            >
              Manage account
            </Link>
          </div>
        </header>
        <main className="px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
