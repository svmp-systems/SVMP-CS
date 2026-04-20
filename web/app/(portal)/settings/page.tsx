import { SettingsForm } from "@/components/portal/settings-form";
import { PageHeader } from "@/components/portal/page-header";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { getServerApi } from "@/services/api/server";

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  try {
    const api = await getServerApi();
    const [me, tenant] = await Promise.all([api.getMe(), api.getTenant()]);
    const params = await searchParams;
    const billingState = params.billing;
    const showBillingRequired =
      billingState === "required" ||
      (Array.isArray(billingState) && billingState.includes("required"));

    return (
      <>
        <PageHeader
          eyebrow="Settings"
          title="Tenant controls for the paid account."
          copy="Manage business profile, users, billing, webhook details, confidence thresholds, and support handoff rules."
        />
        <SettingsForm me={me} tenant={tenant} showBillingRequired={showBillingRequired} />
      </>
    );
  } catch (error) {
    return <PortalErrorScreen error={error} />;
  }
}
