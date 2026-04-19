import { PortalShell } from "@/components/portal/portal-shell";

export const dynamic = "force-dynamic";

export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <PortalShell>{children}</PortalShell>;
}
