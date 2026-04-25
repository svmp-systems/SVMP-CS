import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";

function safeRedirectPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/dashboard";
  }
  return value;
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const nextPath = safeRedirectPath(requestUrl.searchParams.get("next"));

  if (!code) {
    return NextResponse.redirect(new URL("/login?error=callback", request.url));
  }

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(new URL("/login?error=callback", request.url));
  }

  return NextResponse.redirect(new URL(nextPath, request.url));
}
