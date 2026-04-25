import Link from "next/link";
import { ApiError } from "@/services/api/shared";

function apiErrorCopy(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return {
        title: "Sign in again",
        copy: "The portal could not verify your session token with the backend. Go back to login and start a fresh session.",
        action: "Back to login",
        href: "/login",
      };
    }

    if (error.status === 403) {
      return {
        title: "Portal access is not ready",
        copy: "Your login worked, but the backend could not find an active tenant membership for this Supabase account yet. Add or activate the matching membership record before retrying.",
        action: "Back to login",
        href: "/login",
      };
    }

    if (error.status === 402) {
      return {
        title: "Manual approval required",
        copy: "This tenant exists, but its subscription status is not active or trialing yet. Update the tenant billing state in Supabase to unlock operational pages.",
        action: "Open settings",
        href: "/settings?billing=required",
      };
    }

    return {
      title: "Backend request failed",
      copy: `The dashboard API returned ${error.status}. ${error.detail ?? "Check the backend deployment, environment variables, and logs."}`,
      action: "Try dashboard again",
      href: "/dashboard",
    };
  }

  return {
    title: "Backend is not reachable",
    copy: "The portal loaded, but it could not reach the dashboard API. Check NEXT_PUBLIC_API_BASE_URL, backend CORS, and the FastAPI deployment.",
    action: "Try dashboard again",
    href: "/dashboard",
  };
}

export function PortalErrorScreen({ error }: { error: unknown }) {
  const message = apiErrorCopy(error);

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper p-6 text-ink md:p-10">
      <div className="w-full max-w-xl rounded-[8px] border border-line bg-white p-6">
        <p className="text-sm font-semibold text-pine">Customer portal</p>
        <h1 className="mt-3 text-3xl font-semibold">{message.title}</h1>
        <p className="mt-4 text-sm leading-6 text-ink/64">{message.copy}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href={message.href}
            className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine"
          >
            {message.action}
          </Link>
          <Link
            href="/"
            className="rounded-[8px] border border-line px-4 py-3 text-sm font-semibold hover:border-ink"
          >
            Back home
          </Link>
        </div>
      </div>
    </main>
  );
}
