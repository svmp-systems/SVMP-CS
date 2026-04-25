import { redirect } from "next/navigation";

export default async function LegacySsoCallbackPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams();
  const resolved = await searchParams;
  for (const [key, value] of Object.entries(resolved)) {
    if (typeof value === "string") {
      params.set(key, value);
    }
  }

  const suffix = params.toString();
  redirect(suffix ? `/auth/callback?${suffix}` : "/auth/callback");
}
