import {
  governanceLogs,
  integrations,
  knowledgeEntries,
  metrics,
  sessions,
  tenant,
} from "./mock-data";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`SVMP API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  async getTenant() {
    try {
      return await request<typeof tenant>("/api/tenant");
    } catch {
      return tenant;
    }
  },
  async getOverview() {
    try {
      return await request<{ metrics: typeof metrics }>("/api/overview");
    } catch {
      return { metrics };
    }
  },
  async getSessions() {
    try {
      return await request<{ sessions: typeof sessions }>("/api/sessions");
    } catch {
      return { sessions };
    }
  },
  async getKnowledgeBase() {
    try {
      return await request<{ entries: typeof knowledgeEntries }>("/api/knowledge-base");
    } catch {
      return { entries: knowledgeEntries };
    }
  },
  async getGovernance() {
    try {
      return await request<{ logs: typeof governanceLogs }>("/api/governance");
    } catch {
      return { logs: governanceLogs };
    }
  },
  async getIntegrations() {
    try {
      return await request<{ integrations: typeof integrations }>("/api/integrations");
    } catch {
      return { integrations };
    }
  },
};
