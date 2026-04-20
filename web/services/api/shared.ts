import type {
  BrandVoiceResponse,
  GovernanceResponse,
  IntegrationsResponse,
  KnowledgeBaseEntry,
  KnowledgeBaseResponse,
  MeResponse,
  MetricsResponse,
  OverviewResponse,
  SessionDetailResponse,
  SessionsResponse,
  TenantResponse,
  TestQuestionResponse,
} from "./types";

const DEFAULT_API_BASE_URL = "https://api.svmpsystems.com";
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, detail: string | null, message?: string) {
    super(message ?? detail ?? `SVMP CS API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type RequestOptions = RequestInit & {
  token?: string | null;
};

async function parseResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  let payload: unknown = null;

  if (raw) {
    try {
      payload = JSON.parse(raw) as unknown;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : null;
    throw new ApiError(response.status, detail);
  }

  return payload as T;
}

export async function requestJson<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  if (init.token) {
    headers.set("Authorization", `Bearer ${init.token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  return parseResponse<T>(response);
}

export type BrowserApi = ReturnType<typeof createBrowserApi>;

export function createBrowserApi(getToken: () => Promise<string | null>) {
  async function authedRequest<T>(path: string, init: RequestInit = {}) {
    return requestJson<T>(path, {
      ...init,
      token: await getToken(),
    });
  }

  return {
    getMe: () => authedRequest<MeResponse>("/api/me"),
    getTenant: () => authedRequest<TenantResponse>("/api/tenant"),
    saveTenant: (payload: Record<string, unknown>) =>
      authedRequest<TenantResponse>("/api/tenant", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    getOverview: () => authedRequest<OverviewResponse>("/api/overview"),
    getMetrics: () => authedRequest<MetricsResponse>("/api/metrics"),
    getSessions: () => authedRequest<SessionsResponse>("/api/sessions"),
    getSession: (id: string) => authedRequest<SessionDetailResponse>(`/api/sessions/${id}`),
    getKnowledgeBase: (params?: { active?: boolean; search?: string }) => {
      const searchParams = new URLSearchParams();
      if (typeof params?.active === "boolean") {
        searchParams.set("active", String(params.active));
      }
      if (params?.search) {
        searchParams.set("search", params.search);
      }
      const suffix = searchParams.size ? `?${searchParams.toString()}` : "";
      return authedRequest<KnowledgeBaseResponse>(`/api/knowledge-base${suffix}`);
    },
    createKnowledgeEntry: (payload: Omit<KnowledgeBaseEntry, "id" | "createdAt" | "updatedAt">) =>
      authedRequest<KnowledgeBaseEntry>("/api/knowledge-base", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateKnowledgeEntry: (id: string, payload: Partial<KnowledgeBaseEntry>) =>
      authedRequest<KnowledgeBaseEntry>(`/api/knowledge-base/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    deleteKnowledgeEntry: (id: string) =>
      authedRequest<KnowledgeBaseEntry>(`/api/knowledge-base/${id}`, {
        method: "DELETE",
      }),
    testQuestion: (payload: { question: string; domainId?: string; confidenceThreshold?: number }) =>
      authedRequest<TestQuestionResponse>("/api/test-question", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getBrandVoice: () => authedRequest<BrandVoiceResponse>("/api/brand-voice"),
    saveBrandVoice: (payload: Record<string, unknown>) =>
      authedRequest<BrandVoiceResponse>("/api/brand-voice", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    getGovernance: () => authedRequest<GovernanceResponse>("/api/governance"),
    getIntegrations: () => authedRequest<IntegrationsResponse>("/api/integrations"),
    saveWhatsAppIntegration: (payload: Record<string, unknown>) =>
      authedRequest<IntegrationsResponse["integrations"][number]>("/api/integrations/whatsapp", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    createCheckoutSession: () =>
      authedRequest<{ id: string | null; url: string | null }>("/api/billing/create-checkout-session", {
        method: "POST",
      }),
    createPortalSession: () =>
      authedRequest<{ id: string | null; url: string | null }>("/api/billing/create-portal-session", {
        method: "POST",
      }),
  };
}
