"use client";

import { isPreviewAuthMode } from "@/lib/portal-auth-env";
import { createPreviewApi } from "./preview";
import { createBrowserApi } from "./shared";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

export function useBrowserApi() {
  if (isPreviewAuthMode()) {
    return createPreviewApi();
  }

  const supabase = createBrowserSupabaseClient();

  return createBrowserApi(async () => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  });
}
