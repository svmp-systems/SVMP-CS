import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isSupabaseConfigured, isUnsafePreviewAuthEnabled } from "@/lib/portal-auth-env";
import { PREVIEW_SESSION_COOKIE, verifyPreviewSession } from "@/lib/preview-auth";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { createPreviewApi } from "./preview";
import { createBrowserApi, type BrowserApi } from "./shared";

async function requireServerToken() {
  const supabase = await createServerSupabaseClient();
  const { data } = await supabase.auth.getClaims();

  if (!data?.claims?.sub) {
    redirect("/login");
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    redirect("/login");
  }

  return session.access_token;
}

type ServerApi = Omit<BrowserApi, never>;

export async function getServerApi(): Promise<ServerApi> {
  if (isUnsafePreviewAuthEnabled()) {
    const cookieStore = await cookies();
    const session = await verifyPreviewSession(cookieStore.get(PREVIEW_SESSION_COOKIE)?.value);

    if (!session) {
      redirect("/login");
    }

    return createPreviewApi(session);
  }

  if (!isSupabaseConfigured()) {
    redirect("/login?configuration=required");
  }

  return createBrowserApi(requireServerToken);
}
