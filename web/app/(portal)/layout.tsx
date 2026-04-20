import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { PortalShell } from "@/components/portal/portal-shell";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return renderPortalLayout(children);
}

async function renderPortalLayout(children: React.ReactNode) {
  try {
    const api = await getServerApi();
    const [me, tenant] = await Promise.all([api.getMe(), api.getTenant()]);
    return (
      <PortalShell me={me} tenant={tenant}>
        {children}
      </PortalShell>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
