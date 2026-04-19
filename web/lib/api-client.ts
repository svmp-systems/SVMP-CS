import { auth } from "@clerk/nextjs/server";
import {
  governanceLogs,
  integrations,
  knowledgeEntries,
  metrics as demoMetrics,
  sessions as demoSessions,
  tenant as demoTenant,
} from "./mock-data";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.SVMP_API_BASE_URL ?? "";
const USE_DEMO_DATA = process.env.NEXT_PUBLIC_PORTAL_DEMO_DATA !== "0";

type Json = Record<string, unknown>;
type AnyRecord = Record<string, any>;

async function authHeaders() {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  try {
    const session = await auth();
    const token = await session.getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // Login and preview builds can render before Clerk env vars are present.
  }

  return headers;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured");
  }

  const headers = await authHeaders();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...headers,
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `SVMP API request failed: ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep the status-based message.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

async function liveOrDemo<T>(path: string, demo: T): Promise<T> {
  if (!API_BASE_URL && USE_DEMO_DATA) {
    return demo;
  }
  return request<T>(path);
}

function metricCardsFromOverview(overview: Json) {
  const liveMetrics = overview.metrics as Json | undefined;
  if (!liveMetrics) {
    return demoMetrics;
  }

  const deflection = Number(liveMetrics.deflectionRate ?? 0);
  const hoursSaved = Number(liveMetrics.humanHoursSaved ?? 0);
  const activeSessions = Number(liveMetrics.activeSessions ?? 0);
  const activeKb = Number(liveMetrics.activeKnowledgeEntries ?? 0);

  return [
    {
      label: "Deflection rate",
      value: `${Math.round(deflection * 100)}%`,
      detail: "Simple questions handled without a human reply.",
      trend: `${Number(liveMetrics.aiResolved ?? 0)} answered`,
    },
    {
      label: "Human hours saved",
      value: hoursSaved.toFixed(1),
      detail: "Estimated time saved across WhatsApp support.",
      trend: "Live",
    },
    {
      label: "Active sessions",
      value: String(activeSessions),
      detail: "Recent tenant-scoped conversations in the backend.",
      trend: "Tenant scoped",
    },
    {
      label: "Active KB entries",
      value: String(activeKb),
      detail: "Approved entries available for answer matching.",
      trend: "Live",
    },
  ];
}

export const api = {
  async getMe() {
    return liveOrDemo("/api/me", {
      userId: "demo_user",
      email: "owner@stayparfums.com",
      organizationId: "org_demo",
      tenantId: demoTenant.tenantId,
      tenantName: demoTenant.tenantName,
      role: demoTenant.role,
      subscriptionStatus: demoTenant.subscriptionStatus,
      hasActiveSubscription: true,
      allowedActions: [
        "billing.manage",
        "team.manage",
        "integrations.manage",
        "knowledge_base.manage",
        "brand_voice.manage",
        "settings.manage",
        "sessions.read",
        "metrics.read",
        "governance.read",
      ],
    });
  },
  async getTenant(): Promise<AnyRecord> {
    return liveOrDemo<AnyRecord>("/api/tenant", demoTenant);
  },
  async patchTenant(payload: Json) {
    return request<AnyRecord>("/api/tenant", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  async getOverview(): Promise<AnyRecord> {
    const overview = await liveOrDemo<Json>("/api/overview", {
      metrics: demoMetrics,
      recentActivity: governanceLogs,
      setupWarnings: [],
      systemHealth: { status: "active" },
    });
    return {
      ...overview,
      metrics: Array.isArray(overview.metrics)
        ? overview.metrics
        : metricCardsFromOverview(overview),
    };
  },
  async getMetrics(): Promise<AnyRecord> {
    return liveOrDemo<Json>("/api/metrics", {
      decisionCounts: { answered: 0, escalated: 0, closed: 0, total: 0 },
      deflectionRate: 0,
      humanHoursSaved: 0,
    });
  },
  async getSessions(): Promise<{ sessions: AnyRecord[] }> {
    return liveOrDemo<{ sessions: AnyRecord[] }>("/api/sessions", { sessions: demoSessions });
  },
  async getSession(id: string): Promise<AnyRecord> {
    const demoSession = demoSessions.find((session) => session.id === id);
    return liveOrDemo(`/api/sessions/${id}`, {
      session: demoSession,
      governanceLogs: [],
    });
  },
  async getKnowledgeBase(): Promise<{ entries: AnyRecord[] }> {
    return liveOrDemo<{ entries: AnyRecord[] }>("/api/knowledge-base", {
      entries: knowledgeEntries,
    });
  },
  async createKnowledgeEntry(payload: Json) {
    return request<Json>("/api/knowledge-base", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async updateKnowledgeEntry(id: string, payload: Json) {
    return request<Json>(`/api/knowledge-base/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  async deleteKnowledgeEntry(id: string) {
    return request<Json>(`/api/knowledge-base/${id}`, {
      method: "DELETE",
    });
  },
  async getBrandVoice(): Promise<AnyRecord> {
    return liveOrDemo<AnyRecord>("/api/brand-voice", {
      brandVoice: {
        tone: "Warm, polished, premium, concise, and helpful.",
        use: ["concise", "helpful", "confident", "clear"],
        avoid: ["overpromising", "slang", "guaranteed forever", "cheap"],
        escalationStyle:
          "Apologetic and clear. Say that the team will follow up because the answer depends on order-specific or policy-sensitive details.",
        exampleReplies: [],
      },
    });
  },
  async patchBrandVoice(payload: Json) {
    return request<Json>("/api/brand-voice", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  async getGovernance(): Promise<{ logs: AnyRecord[] }> {
    return liveOrDemo<{ logs: AnyRecord[] }>("/api/governance", { logs: governanceLogs });
  },
  async getIntegrations(): Promise<{ integrations: AnyRecord[] }> {
    return liveOrDemo<{ integrations: AnyRecord[] }>("/api/integrations", {
      integrations,
    });
  },
  async patchWhatsAppIntegration(payload: Json) {
    return request<Json>("/api/integrations/whatsapp", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  async testQuestion(payload: Json) {
    return request<Json>("/api/test-question", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async createCheckoutSession() {
    return request<{ url?: string }>("/api/billing/create-checkout-session", {
      method: "POST",
    });
  },
  async createPortalSession() {
    return request<{ url?: string }>("/api/billing/create-portal-session", {
      method: "POST",
    });
  },
};
