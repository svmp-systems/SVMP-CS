import { BrandVoiceEditor } from "@/components/portal/brand-voice-editor";
import { PageHeader } from "@/components/portal/page-header";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import { redirect } from "next/navigation";

export default async function BrandVoicePage() {
  try {
    const api = await getServerApi();
    const { brandVoice } = await api.getBrandVoice();

    return (
      <>
        <PageHeader
          eyebrow="Brand voice"
          title="Control how SVMP CS sounds before it answers customers."
          copy="Set tone, required language, blocked language, and the escalation style used when confidence is low."
        />
        <BrandVoiceEditor initialBrandVoice={brandVoice} />
      </>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
