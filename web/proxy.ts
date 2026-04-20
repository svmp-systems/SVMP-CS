import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest } from "next/server";
import { isClerkConfigured, isUnsafePreviewAuthEnabled } from "@/lib/clerk-env";
import { PREVIEW_SESSION_COOKIE, verifyPreviewSession } from "@/lib/preview-auth";

const isProtectedRoute = createRouteMatcher([
  "/dashboard(.*)",
  "/sessions(.*)",
  "/knowledge-base(.*)",
  "/brand-voice(.*)",
  "/governance(.*)",
  "/metrics(.*)",
  "/integrations(.*)",
  "/settings(.*)",
  "/onboarding(.*)",
]);

const authProxy = clerkMiddleware(async (auth, request) => {
  if (isProtectedRoute(request)) {
    await auth.protect({
      unauthenticatedUrl: "/login",
      unauthorizedUrl: "/login",
    });
  }
});

const previewProxy = async (request: NextRequest) => {
  if (!isProtectedRoute(request)) {
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
  if (!isProtectedRoute(request)) {
    return NextResponse.next({ request });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("configuration", "required");
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
};

export default isClerkConfigured()
  ? authProxy
  : isUnsafePreviewAuthEnabled()
    ? previewProxy
    : lockedProxy;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
