import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher([
  "/dashboard(.*)",
  "/sessions(.*)",
  "/knowledge-base(.*)",
  "/brand-voice(.*)",
  "/governance(.*)",
  "/metrics(.*)",
  "/integrations(.*)",
  "/settings(.*)",
]);

export default clerkMiddleware(async (auth, request) => {
  if (isProtectedRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|png|gif|svg|webp|ico|woff2?|ttf|map)).*)",
    "/(api|trpc)(.*)",
  ],
};
