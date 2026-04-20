import "server-only";

import { auth } from "@clerk/nextjs/server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isClerkConfigured, isUnsafePreviewAuthEnabled } from "@/lib/clerk-env";
import { PREVIEW_SESSION_COOKIE, verifyPreviewSession } from "@/lib/preview-auth";
import { createPreviewApi } from "./preview";
import { createBrowserApi, type BrowserApi } from "./shared";

const clerkJwtTemplate = process.env.CLERK_JWT_TEMPLATE?.trim() || process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE?.trim() || undefined;

async function requireServerToken() {
  const { userId, getToken } = await auth();

  if (!userId) {
    redirect("/login");
  }

  const token = await getToken(clerkJwtTemplate ? { template: clerkJwtTemplate } : undefined);

  if (!token) {
    redirect("/login");
  }

  return token;
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

  if (!isClerkConfigured()) {
    redirect("/login?configuration=required");
  }

  return createBrowserApi(requireServerToken);
}
