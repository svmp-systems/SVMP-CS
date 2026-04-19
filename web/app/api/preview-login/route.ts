import { NextResponse } from "next/server";
import {
  createPreviewSession,
  isAllowedPreviewEmail,
  isPreviewLoginConfigured,
  isValidPreviewPassword,
  PREVIEW_SESSION_COOKIE,
  previewSessionMaxAgeSeconds,
} from "@/lib/preview-auth";
import { isPreviewAuthMode } from "@/lib/clerk-env";

function cleanRedirect(value: unknown) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return "/dashboard";
  }
  return value;
}

export async function POST(request: Request) {
  if (!isPreviewAuthMode()) {
    return NextResponse.json({ error: "Preview login is disabled." }, { status: 404 });
  }

  const body = (await request.json().catch(() => null)) as {
    email?: unknown;
    password?: unknown;
    next?: unknown;
  } | null;
  const email = typeof body?.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body?.password === "string" ? body.password : "";

  if (!isPreviewLoginConfigured()) {
    return NextResponse.json(
      { error: "Built-in portal login is not configured yet. Set PORTAL_PREVIEW_PASSWORD and PORTAL_PREVIEW_AUTH_SECRET in Vercel." },
      { status: 503 },
    );
  }

  if (!email || !isAllowedPreviewEmail(email) || !isValidPreviewPassword(password)) {
    return NextResponse.json({ error: "Email or password is incorrect." }, { status: 401 });
  }

  const token = await createPreviewSession(email);
  const response = NextResponse.json({ redirectTo: cleanRedirect(body?.next) });
  response.cookies.set(PREVIEW_SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: previewSessionMaxAgeSeconds(),
  });
  return response;
}
