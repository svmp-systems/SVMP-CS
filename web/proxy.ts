import { NextResponse, type NextRequest } from "next/server";
import { isSupabaseConfigured, isUnsafePreviewAuthEnabled } from "@/lib/portal-auth-env";
import { PREVIEW_SESSION_COOKIE, verifyPreviewSession } from "@/lib/preview-auth";
import { updateSession } from "@/lib/supabase/proxy";

const protectedRoutePatterns = [
  /^\/dashboard(?:\/.*)?$/,
  /^\/sessions(?:\/.*)?$/,
  /^\/knowledge-base(?:\/.*)?$/,
  /^\/brand-voice(?:\/.*)?$/,
  /^\/governance(?:\/.*)?$/,
  /^\/metrics(?:\/.*)?$/,
  /^\/integrations(?:\/.*)?$/,
  /^\/settings(?:\/.*)?$/,
  /^\/onboarding(?:\/.*)?$/,
];

function isProtectedRoute(pathname: string) {
  return protectedRoutePatterns.some((pattern) => pattern.test(pathname));
}

const previewProxy = async (request: NextRequest) => {
  if (!isProtectedRoute(request.nextUrl.pathname)) {
    return NextResponse.next({ request });
  }

  const session = await verifyPreviewSession(request.cookies.get(PREVIEW_SESSION_COOKIE)?.value);
  if (session) {
    return NextResponse.next({ request });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
};

const lockedProxy = (request: NextRequest) => {
  if (!isProtectedRoute(request.nextUrl.pathname)) {
    return NextResponse.next({ request });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("configuration", "required");
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
};

export async function proxy(request: NextRequest) {
  if (isSupabaseConfigured()) {
    const { response, claims } = await updateSession(request);
    if (!isProtectedRoute(request.nextUrl.pathname)) {
      return response;
    }

    if (claims?.sub) {
      return response;
    }

    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isUnsafePreviewAuthEnabled()) {
    return previewProxy(request);
  }

  return lockedProxy(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
