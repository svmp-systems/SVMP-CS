import type { BrowserApi } from "./shared";
import type {
  BrandVoiceResponse,
  GovernanceLog,
  IntegrationStatus,
  KnowledgeBaseEntry,
  MeResponse,
  SessionSummary,
  TenantResponse,
} from "./types";
import type { PreviewSession } from "@/lib/preview-auth";

const now = "2026-04-19T10:30:00.000Z";

const previewMe: MeResponse = {
  userId: "preview-owner",
  email: "prnvvh@gmail.com",
  organizationId: "stay",
  tenantId: "stay",
  tenantName: "Stay Parfums",
  role: "owner",
  subscriptionStatus: "active",
  hasActiveSubscription: true,
  allowedActions: ["billing", "team", "integrations", "knowledge_base", "brand_voice", "sessions", "metrics"],
};

const previewTenant: TenantResponse = {
  tenantId: "stay",
  tenantName: "Stay Parfums",
  websiteUrl: "https://stayparfums.com",
  industry: "Beauty and fragrance",
  supportEmail: "support@stayparfums.com",
  domains: ["shipping", "returns", "stock", "orders"],
  settings: {
    confidenceThreshold: 0.75,
    autoAnswerEnabled: true,
  },
  brandVoice: {
    tone: "Warm, polished, premium, and concise",
    use: ["concise", "helpful", "confident"],
    avoid: ["overpromising", "slang", "guessing"],
    escalationStyle: "Apologetic and clear, with a direct handoff to the support team.",
    exampleReplies: [
      "I can help with that. Based on the approved policy, your order qualifies for standard shipping.",
      "I do not want to guess on this one, so I am sending it to the Stay Parfums team.",
    ],
  },
  onboarding: {
    status: "completed",
    steps: {
      profile: true,
      brandVoice: true,
      knowledgeBase: true,
      whatsapp: true,
      testConversation: true,
    },
  },
  billing: {
    status: "active",
    hasActiveSubscription: true,
  },
};

const previewKnowledgeBase: KnowledgeBaseEntry[] = [
  {
    id: "kb_shipping",
    domainId: "shipping",
    question: "Do you offer free shipping?",
    answer: "Free shipping is available on eligible orders. If the order does not qualify, SVMP escalates instead of guessing.",
    tags: ["shipping", "checkout"],
    active: true,
    createdAt: "2026-04-15T09:00:00.000Z",
    updatedAt: "2026-04-18T12:10:00.000Z",
  },
  {
    id: "kb_returns",
    domainId: "returns",
    question: "Can I return an opened fragrance?",
    answer: "Opened fragrance returns require human review. SVMP should explain that support will confirm the next step.",
    tags: ["returns", "policy"],
    active: true,
    createdAt: "2026-04-16T09:00:00.000Z",
    updatedAt: "2026-04-18T12:30:00.000Z",
  },
  {
    id: "kb_stock",
    domainId: "stock",
    question: "When will the Discovery Set restock?",
    answer: "The Discovery Set restock date is not confirmed yet. Customers can join the waitlist for the first update.",
    tags: ["stock", "waitlist"],
    active: true,
    createdAt: "2026-04-17T09:00:00.000Z",
    updatedAt: "2026-04-18T14:05:00.000Z",
  },
];

const previewSessions: SessionSummary[] = [
  {
    id: "session_shipping_001",
    provider: "whatsapp",
    status: "resolved",
    dashboardStatus: "resolved",
    customer: "Ava M.",
    question: "Do you offer free shipping?",
    latestMessage: "Do you offer free shipping?",
    answer: "Free shipping is available on eligible orders.",
    source: "kb_shipping",
    confidence: 0.91,
    similarity: 0.88,
    messageCount: 5,
    createdAt: "2026-04-19T08:30:00.000Z",
    updatedAt: "2026-04-19T08:33:00.000Z",
    transcript: [
      { sender: "customer", text: "Do you offer free shipping?", timestamp: "2026-04-19T08:30:00.000Z" },
      { sender: "svmp", text: "Free shipping is available on eligible orders.", timestamp: "2026-04-19T08:31:00.000Z" },
    ],
  },
  {
    id: "session_returns_002",
    provider: "whatsapp",
    status: "escalated",
    dashboardStatus: "escalated",
    customer: "Nina R.",
    question: "Can I return a fragrance I opened yesterday?",
    latestMessage: "Can I return a fragrance I opened yesterday?",
    answer: "This needs human review before SVMP answers.",
    source: "kb_returns",
    confidence: 0.62,
    similarity: 0.6,
    escalationReason: "Return eligibility depends on order condition.",
    messageCount: 4,
    createdAt: "2026-04-19T09:05:00.000Z",
    updatedAt: "2026-04-19T09:07:00.000Z",
    transcript: [
      { sender: "customer", text: "Can I return a fragrance I opened yesterday?", timestamp: "2026-04-19T09:05:00.000Z" },
      { sender: "svmp", text: "I do not want to guess on this one, so I am sending it to the Stay Parfums team.", timestamp: "2026-04-19T09:06:00.000Z" },
    ],
  },
  {
    id: "session_stock_003",
    provider: "whatsapp",
    status: "pending",
    dashboardStatus: "pending",
    customer: "Dev K.",
    question: "Is the Discovery Set available this week?",
    latestMessage: "Is the Discovery Set available this week?",
    source: "kb_stock",
    confidence: 0.78,
    similarity: 0.73,
    messageCount: 3,
    createdAt: "2026-04-19T10:00:00.000Z",
    updatedAt: "2026-04-19T10:02:00.000Z",
    transcript: [
      { sender: "customer", text: "Is the Discovery Set available this week?", timestamp: "2026-04-19T10:00:00.000Z" },
    ],
  },
];

const previewGovernanceLogs: GovernanceLog[] = [
  {
    id: "gov_001",
    decision: "answered",
    question: "Do you offer free shipping?",
    reason: "Matched approved shipping FAQ above confidence threshold.",
    source: "kb_shipping",
    similarity: 0.88,
    groundedness: 0.92,
    safety: 0.98,
    timestamp: "2026-04-19T08:31:00.000Z",
  },
  {
    id: "gov_002",
    decision: "escalated",
    question: "Can I return a fragrance I opened yesterday?",
    reason: "Confidence was below threshold and policy depends on item condition.",
    source: "kb_returns",
    similarity: 0.6,
    groundedness: 0.76,
    safety: 0.96,
    timestamp: "2026-04-19T09:06:00.000Z",
  },
  {
    id: "gov_003",
    action: "knowledge_base.updated",
    actorEmail: "prnvvh@gmail.com",
    resourceType: "knowledge_base",
    resourceId: "kb_stock",
    reason: "Restock answer updated for current waitlist guidance.",
    timestamp: "2026-04-18T14:05:00.000Z",
  },
];

const previewIntegrations: IntegrationStatus[] = [
  {
    tenantId: "stay",
    provider: "whatsapp",
    status: "connected",
    health: "healthy",
    setupWarnings: [],
    metadata: {
      provider: "twilio",
      lastSync: now,
    },
    updatedAt: now,
  },
  {
    tenantId: "stay",
    provider: "slack",
    status: "coming_soon",
    health: "unknown",
    setupWarnings: ["Slack is not part of MVP."],
    updatedAt: now,
  },
  {
    tenantId: "stay",
    provider: "shopify",
    status: "coming_soon",
    health: "unknown",
    setupWarnings: ["Shopify is planned after WhatsApp support is stable."],
    updatedAt: now,
  },
];

function activeKbCount() {
  return previewKnowledgeBase.filter((entry) => entry.active).length;
}

function overviewMetrics() {
  const answered = previewGovernanceLogs.filter((log) => log.decision === "answered").length;
  const escalated = previewGovernanceLogs.filter((log) => log.decision === "escalated").length;
  const total = Math.max(answered + escalated, 1);

  return {
    deflectionRate: answered / total,
    aiResolved: answered,
    humanEscalated: escalated,
    activeSessions: previewSessions.filter((session) => session.dashboardStatus !== "resolved").length,
    activeKnowledgeEntries: activeKbCount(),
    humanHoursSaved: answered * 0.35,
    safetyScore: 98,
  };
}

export function createPreviewApi(session?: Pick<PreviewSession, "email" | "tenantId" | "tenantName" | "role">): BrowserApi {
  const me = {
    ...previewMe,
    email: session?.email ?? previewMe.email,
    tenantId: session?.tenantId ?? previewMe.tenantId,
    tenantName: session?.tenantName ?? previewMe.tenantName,
    role: session?.role ?? previewMe.role,
  };
  const tenant = {
    ...previewTenant,
    tenantId: session?.tenantId ?? previewTenant.tenantId,
    tenantName: session?.tenantName ?? previewTenant.tenantName,
  };

  return {
    getMe: async () => me,
    getTenant: async () => tenant,
    saveTenant: async (payload) => ({
      ...tenant,
      tenantName: typeof payload.tenantName === "string" ? payload.tenantName : tenant.tenantName,
      websiteUrl: typeof payload.websiteUrl === "string" ? payload.websiteUrl : tenant.websiteUrl,
      supportEmail: typeof payload.supportEmail === "string" ? payload.supportEmail : tenant.supportEmail,
      industry: typeof payload.industry === "string" ? payload.industry : tenant.industry,
      settings:
        payload.settings && typeof payload.settings === "object"
          ? { ...tenant.settings, ...payload.settings }
          : tenant.settings,
    }),
    getOverview: async () => ({
      tenantId: tenant.tenantId,
      metrics: overviewMetrics(),
      recentActivity: previewGovernanceLogs,
      setupWarnings: [],
      systemHealth: {
        status: "healthy",
        subscription: "active",
      },
    }),
    getMetrics: async () => {
      const metrics = overviewMetrics();

      return {
        tenantId: tenant.tenantId,
        decisionCounts: {
          answered: metrics.aiResolved,
          escalated: metrics.humanEscalated,
          closed: 0,
          total: metrics.aiResolved + metrics.humanEscalated,
        },
        deflectionRate: metrics.deflectionRate,
        humanHoursSaved: metrics.humanHoursSaved,
      };
    },
    getSessions: async () => ({
      tenantId: tenant.tenantId,
      sessions: previewSessions,
    }),
    getSession: async (id) => ({
      tenantId: tenant.tenantId,
      session: previewSessions.find((session) => session.id === id) ?? previewSessions[0],
      governanceLogs: previewGovernanceLogs,
    }),
    getKnowledgeBase: async (params) => {
      const search = params?.search?.trim().toLowerCase();
      const entries = previewKnowledgeBase.filter((entry) => {
        if (typeof params?.active === "boolean" && entry.active !== params.active) {
          return false;
        }
        if (!search) {
          return true;
        }
        return [entry.domainId, entry.question, entry.answer, ...entry.tags].some((value) =>
          value.toLowerCase().includes(search),
        );
      });

      return {
        tenantId: tenant.tenantId,
        entries,
      };
    },
    createKnowledgeEntry: async (payload) => ({
      ...payload,
      id: `kb_preview_${Date.now()}`,
      createdAt: now,
      updatedAt: now,
    }),
    updateKnowledgeEntry: async (id, payload) => {
      const existing = previewKnowledgeBase.find((entry) => entry.id === id) ?? previewKnowledgeBase[0];
      return {
        ...existing,
        ...payload,
        id,
        updatedAt: now,
      };
    },
    deleteKnowledgeEntry: async (id) => {
      const existing = previewKnowledgeBase.find((entry) => entry.id === id) ?? previewKnowledgeBase[0];
      return {
        ...existing,
        active: false,
        updatedAt: now,
      };
    },
    testQuestion: async (payload) => {
      const question = payload.question.trim();
      const match =
        previewKnowledgeBase.find((entry) => question.toLowerCase().includes(entry.domainId.toLowerCase())) ??
        previewKnowledgeBase[0];

      return {
        tenantId: tenant.tenantId,
        question,
        domainId: match.domainId,
        dryRun: true,
        decision: "answered",
        response: match.answer,
        matchedKnowledgeBaseEntry: match,
        confidenceScore: 0.86,
        threshold: payload.confidenceThreshold ?? 0.75,
        reason: "Preview mode matched this against the sample approved knowledge base.",
        entriesConsidered: previewKnowledgeBase.length,
      };
    },
    getBrandVoice: async (): Promise<BrandVoiceResponse> => ({
      tenantId: tenant.tenantId,
      brandVoice: tenant.brandVoice,
    }),
    saveBrandVoice: async (payload) => ({
      tenantId: tenant.tenantId,
      brandVoice: {
        ...tenant.brandVoice,
        ...payload,
      },
    }),
    getGovernance: async () => ({
      tenantId: tenant.tenantId,
      logs: previewGovernanceLogs,
    }),
    getIntegrations: async () => ({
      tenantId: tenant.tenantId,
      integrations: previewIntegrations,
    }),
    saveWhatsAppIntegration: async (payload) => ({
      ...previewIntegrations[0],
      ...payload,
      provider: "whatsapp",
      tenantId: tenant.tenantId,
      updatedAt: now,
    }),
    createCheckoutSession: async () => ({ id: "preview_checkout", url: "/settings?billing=preview" }),
    createPortalSession: async () => ({ id: "preview_portal", url: "/settings?billing=preview" }),
  };
}
